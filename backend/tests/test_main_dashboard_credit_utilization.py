from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch


ENDPOINT = "/api/get_buyer_credit_limit_utilization"


def test_dashboard_credit_utilization_requires_login(client):
    response = client.get(f"{ENDPOINT}?currency=USD")

    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_dashboard_credit_utilization_returns_normalized_success_envelope(
    logged_in_client,
):
    payload = {
        "currency": "USD",
        "latest_available_data_time": datetime(
            2026, 9, 12, 10, 30, tzinfo=timezone.utc
        ),
        "buyers": [
            {
                "buyer_code": "B001",
                "buyer_name": "Northstar Retail",
                "total_approved_credit_limit": Decimal("150000.00"),
                "used_credit": Decimal("80000.00"),
                "credit_utilization_rate": Decimal("0.5333"),
                "remaining_credit": Decimal("70000.00"),
                "latest_data_time": datetime(
                    2026, 9, 10, 2, 0, tzinfo=timezone.utc
                ),
                "raw_document": {"secret": "must not escape"},
            }
        ],
        "raw_document": {"secret": "must not escape"},
    }

    with patch(
        "backend.app.routes.main.get_mongo", return_value=object()
    ) as get_mongo, patch(
        "backend.app.routes.main.aggregate_buyer_credit_utilization",
        return_value=payload,
    ) as aggregate:
        response = logged_in_client.get(f"{ENDPOINT}?currency=USD")

    assert response.status_code == 200
    assert response.get_json() == {
        "code": 0,
        "msg": "success",
        "data": {
            "currency": "USD",
            "latest_available_data_time": "2026-09-12T10:30:00Z",
            "buyers": [
                {
                    "buyer_code": "B001",
                    "buyer_name": "Northstar Retail",
                    "total_approved_credit_limit": 150000.0,
                    "used_credit": 80000.0,
                    "credit_utilization_rate": 0.5333,
                    "remaining_credit": 70000.0,
                    "latest_data_time": "2026-09-10T02:00:00Z",
                }
            ],
        },
    }
    get_mongo.assert_called_once_with()
    aggregate.assert_called_once_with(get_mongo.return_value, "USD")


def test_dashboard_credit_utilization_rejects_unsupported_currency(
    logged_in_client,
):
    with patch(
        "backend.app.routes.main.aggregate_buyer_credit_utilization"
    ) as aggregate:
        response = logged_in_client.get(f"{ENDPOINT}?currency=JPY")

    assert response.status_code == 400
    assert response.get_json() == {
        "code": 1,
        "msg": "currency must be USD or EUR",
        "data": {},
    }
    aggregate.assert_not_called()


def test_dashboard_credit_utilization_returns_empty_success_with_null_time(
    logged_in_client,
):
    payload = {
        "currency": "EUR",
        "latest_available_data_time": None,
        "buyers": [],
    }

    with patch(
        "backend.app.routes.main.get_mongo", return_value=object()
    ), patch(
        "backend.app.routes.main.aggregate_buyer_credit_utilization",
        return_value=payload,
    ):
        response = logged_in_client.get(f"{ENDPOINT}?currency=EUR")

    assert response.status_code == 200
    assert response.get_json() == {
        "code": 0,
        "msg": "success",
        "data": {
            "currency": "EUR",
            "latest_available_data_time": None,
            "buyers": [],
        },
    }


def test_dashboard_credit_utilization_returns_controlled_error_on_failure(
    logged_in_client,
):
    with patch(
        "backend.app.routes.main.get_mongo", return_value=object()
    ), patch(
        "backend.app.routes.main.aggregate_buyer_credit_utilization",
        side_effect=RuntimeError("raw database failure"),
    ):
        response = logged_in_client.get(f"{ENDPOINT}?currency=USD")

    assert response.status_code == 500
    assert response.get_json() == {
        "code": 1,
        "msg": "Unable to load credit data. Please try again.",
        "data": {},
    }
    assert b"raw database failure" not in response.data
