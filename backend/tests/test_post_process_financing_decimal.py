"""
Regression test for _post_process_financing_records.

Bug: 处理融资单记录时发生错误: '>' not supported between instances of
'Decimal128' and 'int'

Trigger: a financing record whose repayment is 'settled' and whose matching
bank_statement has NO invoice.settlement_date, leaving outstanding_amount as a
raw Decimal128 when it reaches `if outstanding_amount > 0`.
"""
from unittest.mock import MagicMock
from bson import Decimal128

from backend.app.services.import_service import ImportService


def _build_mongo():
    mongo = MagicMock()

    mongo.refactoring_onboard_config.find.return_value = []
    mongo.refactoring_repayment_order.find.return_value = [
        {
            'finance_request_number': 'FR001',
            'repayment_status': 'settled',
            'cumulative_repayment': Decimal128('0'),
        }
    ]
    mongo.refactoring_financing_overview.find.return_value = []

    record = {
        '_id': 'rec1',
        'uid': 'U1',
        'finance_request_number': 'FR001',
        'invoice_number': 'INV001',
        'batch_number': 0,
        'financing_amount': Decimal128('100'),
    }
    mongo.refactoring_financing_order.find.return_value = [{'_id': 'rec1'}]
    mongo.refactoring_financing_order.find_one.return_value = record

    # Bank statement: settled in Air8, but invoice has NO settlement_date,
    # so outstanding_amount stays Decimal128 until the `> 0` comparison.
    mongo.refactoring_bank_statement.find_one.return_value = {
        'invoice': {'seller_reference': 'INV001', 'settlement_date': ''},
        'finance': {
            'status': 'Loan booked',
            'finance_amount': Decimal128('1000'),
            'outstanding_amount': Decimal128('250'),
        },
        'finance_details': {},
    }

    return mongo


def test_post_process_handles_decimal128_outstanding_amount():
    mongo = _build_mongo()
    service = ImportService()

    result = service._post_process_financing_records(mongo=mongo)

    assert result['success'] is True, result.get('message')
    assert result['processed_count'] == 1
    # update_one must have been called (i.e. no exception before reaching it)
    assert mongo.refactoring_financing_order.update_one.called
