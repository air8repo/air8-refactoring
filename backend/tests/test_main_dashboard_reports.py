"""
Tests for backend.app.routes.main get_settlement_schedule / get_db_disbursement:
  - now that aggregate_service no longer filters bank statements by
    finance.status == 'Loan booked' at write time, refactoring_financing_overview
    can contain not-yet-funded records; these two dashboard report functions must
    filter to refactoring_status == 'Loan booked' at read time to preserve the
    pre-existing "only actually loan-booked-or-later" financial totals semantics.
"""
from unittest.mock import patch, MagicMock

from backend.app.routes.main import get_settlement_schedule, get_db_disbursement


def test_get_settlement_schedule_queries_only_loan_booked_records():
    mock_mongo = MagicMock()
    mock_mongo.refactoring_financing_overview.find.return_value = []

    with patch('backend.app.routes.main.get_mongo', return_value=mock_mongo):
        get_settlement_schedule()

    find_filter = mock_mongo.refactoring_financing_overview.find.call_args[0][0]
    assert find_filter == {'refactoring_status': 'Loan booked'}


def test_get_db_disbursement_queries_only_loan_booked_records():
    mock_mongo = MagicMock()
    mock_mongo.refactoring_financing_overview.find.return_value = []

    with patch('backend.app.routes.main.get_mongo', return_value=mock_mongo):
        get_db_disbursement()

    find_filter = mock_mongo.refactoring_financing_overview.find.call_args[0][0]
    assert find_filter == {'refactoring_status': 'Loan booked'}
