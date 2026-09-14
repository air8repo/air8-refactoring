from datetime import datetime, timezone
from decimal import Decimal

import pytest

from backend.app.services.buyer_credit_utilization_service import (
    aggregate_buyer_credit_utilization,
    build_buyer_credit_utilization,
)


UTC = timezone.utc


def _order(invoice_number, buyer_code, buyer_name, currency="USD", uid=None):
    return {
        "uid": uid or f"PAIR-{buyer_code}",
        "finance_request_number": f"FR-{invoice_number}",
        "invoice_number": invoice_number,
        "buyer_code": buyer_code,
        "buyer_name": buyer_name,
        "financing_currency": currency,
    }


def _statement(
    seller_reference,
    creation_time,
    outstanding_amount,
    *,
    status="Loan booked",
    updated_at=None,
    created_at=None,
    system_invoice_id="SID-1",
    currency="USD",
):
    return {
        "invoice": {
            "seller_reference": seller_reference,
            "creation_time": creation_time,
            "system_invoice_id": system_invoice_id,
            "currency": currency,
        },
        "finance": {
            "status": status,
            "outstanding_amount": outstanding_amount,
        },
        "updated_at": updated_at,
        "created_at": created_at,
    }


def _limit(buyer_code, amount, currency="USD", buyer_name=None):
    return {
        "buyer_code": buyer_code,
        "obligor_name": buyer_name or buyer_code,
        "refactoring_limit": amount,
        "credit_limit_currency": currency,
    }


def test_aggregates_latest_booked_items_once_and_returns_chart_time():
    orders = [
        _order("INV-1", "B001", "Northstar Retail"),
        _order("INV-2", "B001", "Northstar Retail"),
        _order("INV-NO", "B999", "Never Booked"),
    ]
    statements = [
        _statement("INV-1", datetime(2026, 9, 10, 1, tzinfo=UTC), Decimal("60000")),
        _statement(
            "INV-1",
            datetime(2026, 9, 10, 0, tzinfo=UTC),
            Decimal("999999"),
            status="Booking requested",
        ),
        _statement("INV-2", datetime(2026, 9, 10, 2, tzinfo=UTC), Decimal("20000")),
        _statement("INV-NO", datetime(2026, 9, 10, 3, tzinfo=UTC), Decimal("50000"), status="Declined"),
    ]
    limits = [
        _limit("B001", Decimal("100000"), buyer_name="Northstar Retail"),
        _limit("B001", Decimal("50000"), buyer_name="Northstar Retail"),
        _limit("B999", Decimal("90000")),
    ]

    result = build_buyer_credit_utilization(orders, statements, limits, "USD")

    assert result["currency"] == "USD"
    assert result["latest_available_data_time"] == datetime(2026, 9, 10, 2, tzinfo=UTC)
    assert [row["buyer_code"] for row in result["buyers"]] == ["B001"]
    assert result["buyers"][0] == {
        "buyer_code": "B001",
        "buyer_name": "Northstar Retail",
        "total_approved_credit_limit": Decimal("150000.00"),
        "used_credit": Decimal("80000.00"),
        "credit_utilization_rate": Decimal("0.5333"),
        "remaining_credit": Decimal("70000.00"),
        "latest_data_time": datetime(2026, 9, 10, 2, tzinfo=UTC),
    }


def test_latest_selection_uses_utc_timestamp_priority_then_full_tie_id():
    order = _order("INV-1", "B001", "Buyer")
    same_creation = datetime(2026, 9, 10, 1, tzinfo=UTC)
    same_update = datetime(2026, 9, 10, 2, tzinfo=UTC)
    statements = [
        _statement(
            "INV-1",
            same_creation,
            Decimal("10"),
            updated_at=datetime(2026, 9, 10, 1, 30, tzinfo=UTC),
            created_at=datetime(2026, 9, 10, 1, tzinfo=UTC),
            system_invoice_id="SID-1",
        ),
        _statement(
            "INV-1",
            same_creation,
            Decimal("20"),
            updated_at=datetime(2026, 9, 10, 1, 30, tzinfo=UTC),
            created_at=datetime(2026, 9, 10, 2, tzinfo=UTC),
            system_invoice_id="SID-2",
        ),
        _statement(
            "INV-1",
            same_creation,
            Decimal("30"),
            updated_at=same_update,
            created_at=datetime(2026, 9, 10, 3, tzinfo=UTC),
            system_invoice_id="SID-3",
        ),
        _statement(
            "INV-1",
            same_creation,
            Decimal("40"),
            updated_at=same_update,
            created_at=datetime(2026, 9, 10, 3, tzinfo=UTC),
            system_invoice_id="SID-9",
        ),
    ]

    result = build_buyer_credit_utilization(
        [order], statements, [_limit("B001", Decimal("100"))], "USD"
    )

    assert result["buyers"][0]["used_credit"] == Decimal("40.00")
    assert result["buyers"][0]["latest_data_time"] == same_creation


def test_full_timestamp_tie_uses_greatest_numeric_system_invoice_id():
    order = _order("INV-1", "B001", "Buyer")
    timestamp = datetime(2026, 9, 10, 1, tzinfo=UTC)
    statements = [
        _statement("INV-1", timestamp, Decimal("9"), system_invoice_id=9),
        _statement("INV-1", timestamp, Decimal("10"), system_invoice_id=10),
    ]

    result = build_buyer_credit_utilization(
        [order], statements, [_limit("B001", Decimal("100"))], "USD"
    )

    assert result["buyers"][0]["used_credit"] == Decimal("10.00")


def test_selected_currency_isolated_and_zero_limits_sort_after_numeric_rates():
    orders = [
        _order("USD-1", "B120", "Over Limit", "USD"),
        _order("EUR-1", "B-EUR", "Euro Buyer", "EUR"),
        _order("USD-2", "B000", "Zero Limit", "USD"),
    ]
    statements = [
        _statement("USD-1", datetime(2026, 9, 12, 9, tzinfo=UTC), Decimal("120")),
        _statement("EUR-1", datetime(2026, 9, 12, 10, tzinfo=UTC), Decimal("900"), currency="EUR"),
        _statement("USD-2", datetime(2026, 9, 12, 11, tzinfo=UTC), Decimal("25")),
    ]
    limits = [
        _limit("B120", Decimal("100"), "USD"),
        _limit("B-EUR", Decimal("1000"), "EUR"),
        _limit("B000", Decimal("0"), "USD"),
    ]

    result = build_buyer_credit_utilization(orders, statements, limits, "USD")

    assert [row["buyer_code"] for row in result["buyers"]] == ["B120", "B000"]
    assert result["buyers"][0]["credit_utilization_rate"] == Decimal("1.2000")
    assert result["buyers"][0]["remaining_credit"] == Decimal("-20.00")
    assert result["buyers"][1]["credit_utilization_rate"] is None
    assert result["buyers"][1]["remaining_credit"] == Decimal("-25.00")
    assert result["latest_available_data_time"] == datetime(2026, 9, 12, 11, tzinfo=UTC)

    euro_result = build_buyer_credit_utilization(orders, statements, limits, "EUR")
    assert [row["buyer_code"] for row in euro_result["buyers"]] == ["B-EUR"]
    assert euro_result["buyers"][0]["used_credit"] == Decimal("900.00")


def test_legacy_limit_without_currency_defaults_to_usd_but_financing_currency_does_not():
    orders = [_order("INV-1", "B001", "Buyer", "EUR")]
    statements = [_statement("INV-1", datetime(2026, 9, 10, tzinfo=UTC), Decimal("10"), currency="EUR")]
    limits = [_limit("B001", Decimal("100"), currency=None)]

    result = build_buyer_credit_utilization(orders, statements, limits, "USD")

    assert result["buyers"] == []


def test_empty_result_and_mongo_boundary_are_read_only():
    class Collection:
        def __init__(self, documents):
            self.documents = documents
            self.calls = 0

        def find(self):
            self.calls += 1
            return list(self.documents)

    class Mongo:
        refactoring_financing_order = Collection([])
        refactoring_bank_statement = Collection([])
        refactoring_onboard_config = Collection([])

    mongo = Mongo()
    result = aggregate_buyer_credit_utilization(mongo, "USD")

    assert result == {
        "currency": "USD",
        "latest_available_data_time": None,
        "buyers": [],
    }
    assert mongo.refactoring_financing_order.calls == 1
    assert mongo.refactoring_bank_statement.calls == 1
    assert mongo.refactoring_onboard_config.calls == 1


@pytest.mark.parametrize("currency", ["GBP", "", None])
def test_rejects_unsupported_currency(currency):
    with pytest.raises(ValueError):
        build_buyer_credit_utilization([], [], [], currency)
