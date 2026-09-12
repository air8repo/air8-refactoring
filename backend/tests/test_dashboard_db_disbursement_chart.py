from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from bson import Decimal128

from backend.app.routes.main import get_db_disbursement


def _overview(*statements, status="Loan booked", batch=1):
    return {
        "refactoring_status": status,
        "loan_submission_batch": batch,
        "bank_statements": list(statements),
    }


def _statement(start_date, amount, interest):
    return {
        "start_date": start_date,
        "finance_amount": amount,
        "interest_amount_usd": interest,
    }


def test_get_db_disbursement_returns_sorted_monthly_averages_and_latest_snapshot():
    mongo = MagicMock()
    mongo.refactoring_financing_overview.find.return_value = [
        _overview(
            _statement(datetime(2026, 1, 15), "100", Decimal128("10")),
            _statement(datetime(2026, 1, 15), 999, 999),
        ),
        _overview(_statement(datetime(2026, 1, 20), 300, 30), batch=2),
        _overview(_statement(datetime(2026, 3, 20), 310, 35), batch=3),
        _overview(_statement(datetime(2026, 1, 20), 900, 90), status="Booking requested", batch=4),
        _overview(_statement(datetime(2026, 1, 20), 700, 70), batch=0),
        _overview(batch=5),
    ]

    with patch("backend.app.routes.main.get_mongo", return_value=mongo):
        result = get_db_disbursement()

    assert mongo.refactoring_financing_overview.find.call_args.args[0] == {
        "refactoring_status": "Loan booked"
    }
    assert result == {
        "months": ["2026-01", "2026-03"],
        "series": {
            "disbursement_amount": [200.0, 310.0],
            "interest": [20.0, 35.0],
        },
    }


def test_get_db_disbursement_assigns_aware_dates_in_asia_shanghai():
    mongo = MagicMock()
    mongo.refactoring_financing_overview.find.return_value = [
        _overview(
            _statement(datetime(2026, 1, 31, 15, 59, 59, tzinfo=timezone.utc), 100, 10)
        ),
        _overview(
            _statement(datetime(2026, 2, 1, tzinfo=timezone.utc), 300, 30),
            batch=2,
        ),
    ]

    with patch("backend.app.routes.main.get_mongo", return_value=mongo):
        result = get_db_disbursement()

    assert result == {
        "months": ["2026-01", "2026-02"],
        "series": {
            "disbursement_amount": [100.0, 300.0],
            "interest": [10.0, 30.0],
        },
    }


def test_get_db_disbursement_returns_empty_chart_shape_without_mongo_or_records():
    empty = {"months": [], "series": {"disbursement_amount": [], "interest": []}}
    with patch("backend.app.routes.main.get_mongo", return_value=None):
        assert get_db_disbursement() == empty

    mongo = MagicMock()
    mongo.refactoring_financing_overview.find.return_value = []
    with patch("backend.app.routes.main.get_mongo", return_value=mongo):
        assert get_db_disbursement() == empty


def test_db_disbursement_api_keeps_authenticated_success_envelope(logged_in_client):
    payload = {
        "months": ["2026-01"],
        "series": {"disbursement_amount": [200.0], "interest": [20.0]},
    }
    with patch("backend.app.routes.main.get_db_disbursement", return_value=payload):
        response = logged_in_client.get("/api/get_db_disbursement")

    assert response.status_code == 200
    assert response.get_json() == {"code": 0, "msg": "success", "data": payload}


def test_db_disbursement_api_keeps_existing_error_envelope(logged_in_client):
    with patch(
        "backend.app.routes.main.get_db_disbursement",
        side_effect=RuntimeError("projection failed"),
    ):
        response = logged_in_client.get("/api/get_db_disbursement")

    assert response.status_code == 200
    assert response.get_json() == {
        "code": 1,
        "msg": "projection failed",
        "data": {},
    }


def test_db_disbursement_api_requires_login(client):
    response = client.get("/api/get_db_disbursement")

    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_dashboard_renders_db_disbursement_line_chart_without_old_table(logged_in_client):
    mongo = MagicMock()
    for collection_name in [
        "refactoring_financing_order",
        "refactoring_repayment_order",
        "refactoring_bank_statement",
        "refactoring_financing_overview",
    ]:
        getattr(mongo, collection_name).count_documents.return_value = 0

    payload = {
        "months": ["2026-01", "2026-03"],
        "series": {
            "disbursement_amount": [200.0, 310.0],
            "interest": [20.0, 35.0],
        },
    }
    with patch("backend.app.routes.main.get_mongo", return_value=mongo), patch(
        "backend.app.routes.main.get_db_disbursement", return_value=payload
    ):
        response = logged_in_client.get("/dashboard")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'id="dbDisbursementChart"' in html
    assert "type: 'line'" in html
    assert '"2026-01"' in html
    assert '"2026-03"' in html
    assert '"2026-02"' not in html
    assert 'id="db_disbursement_body"' not in html
    assert "sum_purchase_price" not in html


def test_dashboard_uses_safe_json_handoff_and_updates_db_chart_theme(logged_in_client):
    mongo = MagicMock()
    for collection_name in [
        "refactoring_financing_order",
        "refactoring_repayment_order",
        "refactoring_bank_statement",
        "refactoring_financing_overview",
    ]:
        getattr(mongo, collection_name).count_documents.return_value = 0

    payload = {
        "months": ["2026-01</script><script>alert(1)</script>"],
        "series": {
            "disbursement_amount": [200.0],
            "interest": [20.0],
        },
    }
    with patch("backend.app.routes.main.get_mongo", return_value=mongo), patch(
        "backend.app.routes.main.get_db_disbursement", return_value=payload
    ):
        response = logged_in_client.get("/dashboard")

    html = response.get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html
    assert 'id="dbDisbursementData"' in html
    assert "dbDisbursementChart.options.scales.x.grid.color" in html
    assert "dbDisbursementChart.options.scales.y.grid.color" in html
    assert "dbDisbursementChart.options.plugins.tooltip.backgroundColor" in html
    assert "dbDisbursementChart.update()" in html


def test_dashboard_keeps_existing_no_data_default_without_empty_chart(logged_in_client):
    mongo = MagicMock()
    for collection_name in [
        "refactoring_financing_order",
        "refactoring_repayment_order",
        "refactoring_bank_statement",
        "refactoring_financing_overview",
    ]:
        getattr(mongo, collection_name).count_documents.return_value = 0

    empty_payload = {
        "months": [],
        "series": {"disbursement_amount": [], "interest": []},
    }
    with patch("backend.app.routes.main.get_mongo", return_value=mongo), patch(
        "backend.app.routes.main.get_db_disbursement", return_value=empty_payload
    ):
        response = logged_in_client.get("/dashboard")

    html = response.get_data(as_text=True)
    assert 'id="dbDisbursementChart"' not in html
    assert "暂无数据" in html
    assert 'id="dataDistributionChart"' in html
    assert "Settlement Schedule" not in html
