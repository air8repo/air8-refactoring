"""
Tests for the shared aggregation helpers:
  - _pick_latest_statement: pick the newest bank_statement by invoice.creation_time
  - _build_refactor_snapshot_fields: derive top-level overview fields from it
"""
from datetime import datetime
from bson import Decimal128

from backend.app.services.aggregate_service import (
    _pick_latest_statement,
    _build_refactor_snapshot_fields,
)


def _statement(creation_time, **overrides):
    base = {
        'invoice': {
            'creation_time': creation_time,
            'status': 'Financing confirmed',
            'currency': 'USD',
            'system_invoice_id': 'SID-1',
        },
        'finance': {
            'status': 'Loan booked',
            'finance_amount': Decimal128('100'),
            'interest_rate_pct': Decimal128('5.1'),
            'interest_amount': Decimal128('10'),
            'purchase_price': Decimal128('90'),
        },
        'settlement_status': 'Not settled',
    }
    base.update(overrides)
    return base


class TestPickLatestStatement:
    def test_empty_list_returns_none(self):
        assert _pick_latest_statement([]) is None

    def test_single_statement_returned(self):
        s = _statement(datetime(2026, 1, 1))
        assert _pick_latest_statement([s]) is s

    def test_picks_newest_by_creation_time(self):
        older = _statement(datetime(2026, 1, 1), invoice={
            'creation_time': datetime(2026, 1, 1), 'status': 'old', 'currency': 'USD', 'system_invoice_id': 'OLD'
        })
        newer = _statement(datetime(2026, 6, 1), invoice={
            'creation_time': datetime(2026, 6, 1), 'status': 'new', 'currency': 'USD', 'system_invoice_id': 'NEW'
        })
        result = _pick_latest_statement([older, newer])
        assert result['invoice']['system_invoice_id'] == 'NEW'

    def test_missing_creation_time_sorts_before_present_ones(self):
        no_time = _statement(None, invoice={
            'creation_time': None, 'status': 'x', 'currency': 'USD', 'system_invoice_id': 'NO-TIME'
        })
        has_time = _statement(datetime(2026, 1, 1), invoice={
            'creation_time': datetime(2026, 1, 1), 'status': 'y', 'currency': 'USD', 'system_invoice_id': 'HAS-TIME'
        })
        result = _pick_latest_statement([no_time, has_time])
        assert result['invoice']['system_invoice_id'] == 'HAS-TIME'


class TestBuildRefactorSnapshotFields:
    def test_none_statement_returns_empty_defaults(self):
        fields = _build_refactor_snapshot_fields(None)
        assert fields['refactoring_status'] == 'init'
        assert fields['refactor_id'] == ''
        assert fields['refactor_portal_status'] == ''
        assert fields['refactor_settlement_status'] == ''
        assert fields['refactor_currency'] == ''
        assert fields['refactor_amount'] is None
        assert fields['refactor_interest_rate_pct'] is None
        assert fields['refactor_interest_amount'] is None
        assert fields['refactor_purchase_price'] is None

    def test_maps_fields_from_statement(self):
        s = _statement(datetime(2026, 1, 1))
        fields = _build_refactor_snapshot_fields(s)
        assert fields['refactoring_status'] == 'Loan booked'          # finance.status
        assert fields['refactor_id'] == 'SID-1'                       # invoice.system_invoice_id
        assert fields['refactor_portal_status'] == 'Financing confirmed'  # invoice.status
        assert fields['refactor_settlement_status'] == 'Not settled'
        assert fields['refactor_currency'] == 'USD'
        assert fields['refactor_amount'] == Decimal128('100')
        assert fields['refactor_interest_rate_pct'] == Decimal128('5.1')
        assert fields['refactor_interest_amount'] == Decimal128('10')
        assert fields['refactor_purchase_price'] == Decimal128('90')


from backend.app.services.aggregate_service import AggregateService


class TestFormatBankStatement:
    def test_includes_settlement_status(self):
        statement = {
            'invoice': {'system_invoice_id': 'SID-1', 'status': 'Financing confirmed', 'currency': 'USD'},
            'finance': {'status': 'Loan booked', 'db_finance_ref': 'REF-1'},
            'usd_details': {},
            'settlement_status': 'Initiated',
        }
        result = AggregateService()._format_bank_statement(statement)
        assert result['settlement_status'] == 'Initiated'
        assert result['system_invoice_id'] == 'SID-1'
        assert result['db_finance_ref'] == 'REF-1'

    def test_missing_settlement_status_is_none(self):
        statement = {'invoice': {}, 'finance': {}, 'usd_details': {}}
        result = AggregateService()._format_bank_statement(statement)
        assert result['settlement_status'] is None
