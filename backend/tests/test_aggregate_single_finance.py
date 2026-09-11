"""
Tests for AggregateService._aggregate_single_finance:
  - no longer filters by finance.status == 'Loan booked'
  - picks the latest statement by invoice.creation_time when multiple exist
  - settled_in_air8 must come from financing_order, not be hardcoded blank
"""
from unittest.mock import patch, MagicMock
from datetime import datetime
from bson import Decimal128

from backend.app.services.aggregate_service import AggregateService


def _financing_order(**overrides):
    base = {
        'finance_request_number': 'RZ001',
        'invoice_number': 'INV-001',
        'buyer_code': 'B001',
        'buyer_name': 'Buyer Co',
        'supplier_code': 'S001',
        'supplier_name': 'Seller Co',
        'insurer': 'DB Insurance',
        'trade_amount': Decimal128('1000'),
        'financing_amount_trade_currency': Decimal128('950'),
        'financing_interest': Decimal128('12.5'),
        'actual_tenor': 39,
        'collection_period': 5,
        'settled_in_air8': 'Settled',
        'status': 'Active',
        'batch_number': 0,
    }
    base.update(overrides)
    return base


def _bank_statement(db_ref, creation_time, finance_status):
    return {
        'invoice': {
            'seller_reference': 'INV-001',
            'creation_time': creation_time,
            'status': 'Financing confirmed',
            'currency': 'USD',
            'system_invoice_id': f'SID-{creation_time.isoformat()}',
        },
        'finance': {
            'status': finance_status,
            'db_finance_ref': db_ref,
            'finance_amount': Decimal128('100'),
            'interest_rate_pct': Decimal128('5.1'),
            'interest_amount': Decimal128('10'),
            'purchase_price': Decimal128('90'),
        },
        'usd_details': {},
        'settlement_status': 'Not settled',
    }


def _run(financing_order, bank_statements, repayments=None):
    mock_mongo = MagicMock()
    mock_mongo.refactoring_financing_order.find_one.return_value = financing_order
    mock_mongo.refactoring_repayment_order.find.return_value = repayments or []
    mock_mongo.refactoring_bank_statement.find.return_value = bank_statements
    mock_mongo.refactoring_financing_overview.find_one.return_value = None

    with patch('backend.app.services.aggregate_service.get_mongo', return_value=mock_mongo):
        AggregateService()._aggregate_single_finance('RZ001')

    return mock_mongo.refactoring_financing_overview.insert_one.call_args[0][0]


def test_non_loan_booked_statement_is_included():
    order = _financing_order()
    statement = _bank_statement('RZ001', datetime(2026, 1, 1), 'Booking requested')
    record = _run(order, [statement])
    assert record['refactoring_status'] == 'Booking requested'


def test_query_no_longer_filters_by_loan_booked_status():
    order = _financing_order()
    mock_mongo = MagicMock()
    mock_mongo.refactoring_financing_order.find_one.return_value = order
    mock_mongo.refactoring_repayment_order.find.return_value = []
    mock_mongo.refactoring_bank_statement.find.return_value = []
    mock_mongo.refactoring_financing_overview.find_one.return_value = None
    with patch('backend.app.services.aggregate_service.get_mongo', return_value=mock_mongo):
        AggregateService()._aggregate_single_finance('RZ001')
    find_filter = mock_mongo.refactoring_bank_statement.find.call_args[0][0]
    assert find_filter == {}


def test_picks_latest_statement_by_creation_time():
    order = _financing_order()
    older = _bank_statement('RZ001', datetime(2026, 1, 1), 'Booking requested')
    newer = _bank_statement('RZ001', datetime(2026, 6, 1), 'Loan booked')
    record = _run(order, [older, newer])
    assert record['refactoring_status'] == 'Loan booked'
    assert len(record['bank_statements']) == 2


def test_settled_in_air8_sourced_from_financing_order_not_hardcoded_blank():
    order = _financing_order(settled_in_air8='Settled')
    statement = _bank_statement('RZ001', datetime(2026, 1, 1), 'Loan booked')
    record = _run(order, [statement])
    assert record['settled_in_air8'] == 'Settled'


def test_totals_use_only_latest_statement_not_sum_of_all():
    """同一融资单多条历史阶段性对账单时，totals 不应把各阶段快照的金额加总"""
    order = _financing_order()
    older = _bank_statement('RZ001', datetime(2026, 1, 1), 'Booking requested')
    older['usd_details'] = {'interest_amount': Decimal128('999')}
    newer = _bank_statement('RZ001', datetime(2026, 6, 1), 'Loan booked')
    newer['usd_details'] = {'interest_amount': Decimal128('10')}
    record = _run(order, [older, newer])
    assert record['totals']['interest_amount_usd'] == Decimal128('10')  # 只取最新一条，不是 999+10


def test_new_fields_present():
    order = _financing_order()
    statement = _bank_statement('RZ001', datetime(2026, 1, 1), 'Loan booked')
    record = _run(order, [statement])
    assert record['funder'] == 'DB Insurance'
    assert record['financing_amount_trade_currency'] == Decimal128('950')
    assert record['interest_amount_trade_currency'] == Decimal128('12.5')
    assert record['order_details']['actual_tenor'] == 39
    assert record['order_details']['collection_period'] == 5
    assert record['refactor_id'] == statement['invoice']['system_invoice_id']


def test_bank_statements_sorted_newest_first():
    """bank_statements[0] 必须始终是最新一条（按 invoice.creation_time），无论原始顺序如何，
    以维持下游 export_service.py / main.py 对 bank_statements[0] 的既有约定"""
    order = _financing_order()
    newer = _bank_statement('RZ001', datetime(2026, 6, 1), 'Loan booked')
    older = _bank_statement('RZ001', datetime(2026, 1, 1), 'Booking requested')
    # 原始顺序故意把旧的对账单放在前面
    record = _run(order, [older, newer])
    assert record['bank_statements'][0]['system_invoice_id'] == newer['invoice']['system_invoice_id']
    assert record['bank_statements'][1]['system_invoice_id'] == older['invoice']['system_invoice_id']


def test_interest_rate_pct_present_and_sourced_from_financing_order():
    """_aggregate_single_finance 使用 replace_one 整体替换记录，若遗漏 interest_rate_pct 会导致
    手动重新聚合后该字段被静默删除，前端『利率%』列显示为空"""
    order = _financing_order(interest_rate_fee_charge=Decimal128('4.25'))
    statement = _bank_statement('RZ001', datetime(2026, 1, 1), 'Loan booked')
    record = _run(order, [statement])
    assert record['interest_rate_pct'] == Decimal128('4.25')
