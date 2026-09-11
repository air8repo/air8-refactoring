"""
Tests for AggregateService.aggregate_financing_overview:
  - no longer filters bank statements by finance.status == 'Loan booked'
  - groups multiple statements per finance request and keeps the latest snapshot
  - fixes refactoring_status / refactor_id / financing_amount_trade_currency sourcing
"""
from unittest.mock import patch, MagicMock
from datetime import datetime
from bson import Decimal128

from backend.app.services.aggregate_service import AggregateService


def _financing_order(**overrides):
    base = {
        '_id': 'order-1',
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
        'settled_in_air8': 'Pending for Repayment',
        'status': 'Active',
        'batch_number': 0,
    }
    base.update(overrides)
    return base


def _bank_statement(seller_reference, creation_time, finance_status, **overrides):
    base = {
        'invoice': {
            'seller_reference': seller_reference,
            'creation_time': creation_time,
            'status': 'Financing confirmed',
            'currency': 'USD',
            'system_invoice_id': f'SID-{creation_time.isoformat()}',
        },
        'finance': {
            'status': finance_status,
            'db_finance_ref': 'REF-1',
            'finance_amount': Decimal128('100'),
            'interest_rate_pct': Decimal128('5.1'),
            'interest_amount': Decimal128('10'),
            'purchase_price': Decimal128('90'),
        },
        'usd_details': {},
        'settlement_status': 'Not settled',
    }
    base.update(overrides)
    return base


def _run_aggregate(financing_orders, bank_statements, repayments=None):
    mock_mongo = MagicMock()
    mock_mongo.refactoring_bank_statement.count_documents.return_value = len(bank_statements)
    mock_mongo.refactoring_bank_statement.distinct.return_value = list({
        s['invoice']['seller_reference'] for s in bank_statements
    })
    mock_mongo.refactoring_financing_order.find.return_value = financing_orders
    mock_mongo.refactoring_repayment_order.find.return_value = repayments or []

    mock_cursor = MagicMock()
    mock_cursor.__iter__.return_value = iter(bank_statements)
    mock_mongo.refactoring_bank_statement.find.return_value = mock_cursor

    mock_mongo.refactoring_financing_overview.count_documents.return_value = 1
    bulk_result = MagicMock(upserted_count=1, modified_count=0)
    mock_mongo.refactoring_financing_overview.bulk_write.return_value = bulk_result

    with patch('backend.app.services.aggregate_service.get_mongo', return_value=mock_mongo):
        AggregateService().aggregate_financing_overview()

    ops = mock_mongo.refactoring_financing_overview.bulk_write.call_args[0][0]
    return {op._filter['finance_request_number']: op._doc['$set'] for op in ops}


def test_non_loan_booked_statement_is_aggregated():
    """去除 Loan booked 过滤后，早期审批阶段的对账单也应被聚合"""
    order = _financing_order()
    statement = _bank_statement('INV-001', datetime(2026, 1, 1), 'Booking requested')
    records = _run_aggregate([order], [statement])
    assert 'RZ001' in records


def test_query_no_longer_filters_by_loan_booked_status():
    mock_mongo = MagicMock()
    mock_mongo.refactoring_bank_statement.count_documents.return_value = 0
    with patch('backend.app.services.aggregate_service.get_mongo', return_value=mock_mongo):
        AggregateService().aggregate_financing_overview()
    count_call_filter = mock_mongo.refactoring_bank_statement.count_documents.call_args[0][0]
    assert count_call_filter == {}


def test_multiple_statements_pick_latest_by_creation_time():
    order = _financing_order()
    older = _bank_statement('INV-001', datetime(2026, 1, 1), 'Booking requested')
    newer = _bank_statement('INV-001', datetime(2026, 6, 1), 'Loan booked')
    records = _run_aggregate([order], [older, newer])
    record = records['RZ001']
    assert record['refactoring_status'] == 'Loan booked'
    assert len(record['bank_statements']) == 2  # 历史记录全部保留


def test_refactoring_status_sourced_from_finance_status_not_invoice_status():
    order = _financing_order()
    statement = _bank_statement('INV-001', datetime(2026, 1, 1), 'Loan booked')
    statement['invoice']['status'] = 'Financing confirmed'
    records = _run_aggregate([order], [statement])
    assert records['RZ001']['refactoring_status'] == 'Loan booked'
    assert records['RZ001']['refactor_portal_status'] == 'Financing confirmed'


def test_refactor_id_sourced_from_system_invoice_id_not_db_finance_ref():
    order = _financing_order()
    statement = _bank_statement('INV-001', datetime(2026, 1, 1), 'Loan booked')
    records = _run_aggregate([order], [statement])
    assert records['RZ001']['refactor_id'] == statement['invoice']['system_invoice_id']


def test_financing_amount_trade_currency_sourced_from_order_field_not_trade_amount():
    order = _financing_order(financing_amount_trade_currency=Decimal128('950'), trade_amount=Decimal128('1000'))
    statement = _bank_statement('INV-001', datetime(2026, 1, 1), 'Loan booked')
    records = _run_aggregate([order], [statement])
    assert records['RZ001']['financing_amount_trade_currency'] == Decimal128('950')


def test_new_fields_present():
    order = _financing_order()
    statement = _bank_statement('INV-001', datetime(2026, 1, 1), 'Loan booked')
    records = _run_aggregate([order], [statement])
    record = records['RZ001']
    assert record['funder'] == 'DB Insurance'
    assert record['interest_amount_trade_currency'] == Decimal128('12.5')
    assert record['order_details']['actual_tenor'] == 39
    assert record['order_details']['collection_period'] == 5


def test_bank_statements_sorted_newest_first():
    """bank_statements[0] 必须始终是最新一条（按 invoice.creation_time），无论原始顺序如何，
    以维持下游 export_service.py / main.py 对 bank_statements[0] 的既有约定"""
    order = _financing_order()
    newer = _bank_statement('INV-001', datetime(2026, 6, 1), 'Loan booked')
    older = _bank_statement('INV-001', datetime(2026, 1, 1), 'Booking requested')
    # 原始顺序故意把旧的对账单放在前面
    records = _run_aggregate([order], [older, newer])
    record = records['RZ001']
    assert record['bank_statements'][0]['system_invoice_id'] == newer['invoice']['system_invoice_id']
    assert record['bank_statements'][1]['system_invoice_id'] == older['invoice']['system_invoice_id']


def test_totals_use_only_latest_statement_not_sum_of_all():
    """同一融资单多条历史阶段性对账单时，totals 不应把各阶段快照的金额加总"""
    order = _financing_order()
    older = _bank_statement(
        'INV-001', datetime(2026, 1, 1), 'Booking requested',
        usd_details={'interest_amount': Decimal128('999')},
    )
    newer = _bank_statement(
        'INV-001', datetime(2026, 6, 1), 'Loan booked',
        usd_details={'interest_amount': Decimal128('10')},
    )
    records = _run_aggregate([order], [older, newer])
    totals = records['RZ001']['totals']
    assert totals['interest_amount_usd'] == Decimal128('10')  # 只取最新一条，不是 999+10
