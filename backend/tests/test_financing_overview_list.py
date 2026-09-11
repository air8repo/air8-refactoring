"""
Tests for GET /maintenance/financing-overview (list page)
and POST /maintenance/financing-overview/export (Excel export).
"""
import pytest
from unittest.mock import patch, MagicMock
from bson import Decimal128
from datetime import datetime


ENDPOINT = '/maintenance/financing-overview'
EXPORT_ENDPOINT = '/maintenance/financing-overview/export'

MOCK_OVERVIEW_RECORD = {
    '_id': 'fake_id',
    'finance_request_number': 'RZ202512110000000094',
    'buyer_name': 'Test Buyer',
    'buyer_erp_id': 'B001',
    'seller_name': 'Test Seller',
    'seller_erp_id': 'S001',
    'funder': 'DB Insurance',
    'summary_status': 'Active',
    'refactoring_status': 'Loan booked',
    'refactor_portal_status': 'Financing confirmed',
    'refactor_settlement_status': 'Not settled',
    'refactor_currency': 'USD',
    'refactor_amount': Decimal128('2548.10'),
    'refactor_interest_rate_pct': Decimal128('5.1694'),
    'refactor_interest_amount': Decimal128('7.32'),
    'refactor_purchase_price': Decimal128('2540.78'),
    'refactor_id': 'GFM2638847',
    'settled_in_air8': 'Pending for Repayment',
    'loan_submission_batch': 1,
    'bank_source': 'DB',
    'financing_amount_trade_currency': Decimal128('100000.50'),
    'interest_amount_trade_currency': Decimal128('33.70'),
    'interest_rate_pct': 3.5,
    'db_loan_settle_date': datetime(2025, 6, 30),
    'updated_at': datetime(2025, 6, 1),
    'order_details': {
        'invoice_number': 'INV-2025-001',
        'currency': 'USD',
        'due_date': datetime(2025, 7, 15),
        'maturity_date': datetime(2025, 8, 15),
        'original_amount': Decimal128('2831.22'),
        'actual_tenor': 39,
        'collection_period': 5,
    },
    'totals': {
        'wip_pending_amount': Decimal128('5000.00'),
    },
    'bank_statements': [],
    'repayments': [],
}


def _mock_chain(records):
    """Create a chainable mock: find().sort().skip().limit() -> records"""
    mock_cursor = MagicMock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = records
    return mock_cursor


class TestFinancingOverviewListAuth:
    """Authentication tests"""

    def test_requires_login(self, client):
        resp = client.get(ENDPOINT)
        assert resp.status_code == 302
        assert '/auth/login' in resp.headers.get('Location', '')

    def test_export_requires_login(self, client):
        resp = client.post(EXPORT_ENDPOINT)
        assert resp.status_code == 302
        assert '/auth/login' in resp.headers.get('Location', '')


class TestFinancingOverviewList:
    """List page tests"""

    def test_loads_with_empty_data(self, logged_in_client, mock_mongo):
        mock_mongo.refactoring_financing_overview.find.return_value = _mock_chain([])
        mock_mongo.refactoring_financing_overview.count_documents.return_value = 0
        mock_mongo.refactoring_financing_overview.distinct.return_value = []

        resp = logged_in_client.get(ENDPOINT)
        assert resp.status_code == 200

    def test_loads_with_data(self, logged_in_client, mock_mongo):
        mock_mongo.refactoring_financing_overview.find.return_value = _mock_chain(
            [MOCK_OVERVIEW_RECORD.copy()]
        )
        mock_mongo.refactoring_financing_overview.count_documents.return_value = 1
        mock_mongo.refactoring_financing_overview.distinct.return_value = []

        resp = logged_in_client.get(ENDPOINT)
        assert resp.status_code == 200
        assert b'RZ202512110000000094' in resp.data

    def test_decimal128_converted(self, logged_in_client, mock_mongo):
        mock_mongo.refactoring_financing_overview.find.return_value = _mock_chain(
            [MOCK_OVERVIEW_RECORD.copy()]
        )
        mock_mongo.refactoring_financing_overview.count_documents.return_value = 1
        mock_mongo.refactoring_financing_overview.distinct.return_value = []

        resp = logged_in_client.get(ENDPOINT)
        assert resp.status_code == 200
        assert b'100,000.50' in resp.data

    def test_nested_fields_flattened(self, logged_in_client, mock_mongo):
        mock_mongo.refactoring_financing_overview.find.return_value = _mock_chain(
            [MOCK_OVERVIEW_RECORD.copy()]
        )
        mock_mongo.refactoring_financing_overview.count_documents.return_value = 1
        mock_mongo.refactoring_financing_overview.distinct.return_value = []

        resp = logged_in_client.get(ENDPOINT)
        assert resp.status_code == 200
        assert b'INV-2025-001' in resp.data

    def test_filter_by_finance_request_number(self, logged_in_client, mock_mongo):
        mock_mongo.refactoring_financing_overview.find.return_value = _mock_chain([])
        mock_mongo.refactoring_financing_overview.count_documents.return_value = 0
        mock_mongo.refactoring_financing_overview.distinct.return_value = []

        logged_in_client.get(f'{ENDPOINT}?finance_request_number=RZ2025')

        call_args = mock_mongo.refactoring_financing_overview.find.call_args
        filters = call_args[0][0]
        assert 'finance_request_number' in filters
        assert filters['finance_request_number']['$regex'] == 'RZ2025'

    def test_filter_by_invoice_number(self, logged_in_client, mock_mongo):
        mock_mongo.refactoring_financing_overview.find.return_value = _mock_chain([])
        mock_mongo.refactoring_financing_overview.count_documents.return_value = 0
        mock_mongo.refactoring_financing_overview.distinct.return_value = []

        logged_in_client.get(f'{ENDPOINT}?invoice_number=INV-2025')

        call_args = mock_mongo.refactoring_financing_overview.find.call_args
        filters = call_args[0][0]
        assert 'order_details.invoice_number' in filters
        # re.escape() 会转义连字符等字符（不影响实际匹配效果），因此这里按字面匹配校验而非精确相等
        import re
        assert re.search(filters['order_details.invoice_number']['$regex'], 'INV-2025') is not None

    def test_filter_by_refactoring_status(self, logged_in_client, mock_mongo):
        mock_mongo.refactoring_financing_overview.find.return_value = _mock_chain([])
        mock_mongo.refactoring_financing_overview.count_documents.return_value = 0
        mock_mongo.refactoring_financing_overview.distinct.return_value = []

        logged_in_client.get(f'{ENDPOINT}?refactoring_status=Pending')

        call_args = mock_mongo.refactoring_financing_overview.find.call_args
        filters = call_args[0][0]
        assert filters['refactoring_status'] == 'Pending'

    def test_filter_by_buyer_name(self, logged_in_client, mock_mongo):
        mock_mongo.refactoring_financing_overview.find.return_value = _mock_chain([])
        mock_mongo.refactoring_financing_overview.count_documents.return_value = 0
        mock_mongo.refactoring_financing_overview.distinct.return_value = []

        logged_in_client.get(f'{ENDPOINT}?buyer_name=Test')

        call_args = mock_mongo.refactoring_financing_overview.find.call_args
        filters = call_args[0][0]
        assert 'buyer_name' in filters
        assert filters['buyer_name']['$regex'] == 'Test'

    def test_filter_by_buyer_name_with_regex_metacharacters_matches_literally(self, logged_in_client, mock_mongo):
        """回归测试：买方名称含正则元字符（如括号）时，搜索应按字面匹配，而不是被当成正则语法。
        例如 'BORDIC (PTY) LTD' 中的括号若不转义，会被 Mongo 当成正则分组，
        导致永远搜不到真正含有这些括号的记录。"""
        import re
        mock_mongo.refactoring_financing_overview.find.return_value = _mock_chain([])
        mock_mongo.refactoring_financing_overview.count_documents.return_value = 0
        mock_mongo.refactoring_financing_overview.distinct.return_value = []

        buyer_name = 'BORDIC (PTY) LTD'
        logged_in_client.get(f'{ENDPOINT}?buyer_name={buyer_name}')

        call_args = mock_mongo.refactoring_financing_overview.find.call_args
        filters = call_args[0][0]
        built_pattern = filters['buyer_name']['$regex']
        # 构造出来的正则必须能按字面匹配含括号的真实买方名称
        assert re.search(built_pattern, buyer_name, re.IGNORECASE) is not None

    def test_combined_filters(self, logged_in_client, mock_mongo):
        mock_mongo.refactoring_financing_overview.find.return_value = _mock_chain([])
        mock_mongo.refactoring_financing_overview.count_documents.return_value = 0
        mock_mongo.refactoring_financing_overview.distinct.return_value = []

        logged_in_client.get(
            f'{ENDPOINT}?finance_request_number=RZ&refactoring_status=Pending&seller_name=Seller'
        )

        call_args = mock_mongo.refactoring_financing_overview.find.call_args
        filters = call_args[0][0]
        assert 'finance_request_number' in filters
        assert filters['refactoring_status'] == 'Pending'
        assert 'seller_name' in filters

    def test_no_filters_returns_all(self, logged_in_client, mock_mongo):
        mock_mongo.refactoring_financing_overview.find.return_value = _mock_chain([])
        mock_mongo.refactoring_financing_overview.count_documents.return_value = 0
        mock_mongo.refactoring_financing_overview.distinct.return_value = []

        logged_in_client.get(ENDPOINT)

        call_args = mock_mongo.refactoring_financing_overview.find.call_args
        filters = call_args[0][0]
        assert filters == {}

    def test_pagination_default_page(self, logged_in_client, mock_mongo):
        mock_mongo.refactoring_financing_overview.find.return_value = _mock_chain([])
        mock_mongo.refactoring_financing_overview.count_documents.return_value = 0
        mock_mongo.refactoring_financing_overview.distinct.return_value = []

        logged_in_client.get(ENDPOINT)

        cursor = mock_mongo.refactoring_financing_overview.find.return_value.sort.return_value
        cursor.skip.assert_called_with(0)
        cursor.skip.return_value.limit.assert_called_with(20)

    def test_pagination_page_2(self, logged_in_client, mock_mongo):
        mock_mongo.refactoring_financing_overview.find.return_value = _mock_chain([])
        mock_mongo.refactoring_financing_overview.count_documents.return_value = 25
        mock_mongo.refactoring_financing_overview.distinct.return_value = []

        logged_in_client.get(f'{ENDPOINT}?page=2')

        cursor = mock_mongo.refactoring_financing_overview.find.return_value.sort.return_value
        cursor.skip.assert_called_with(20)


class TestFinancingOverviewExport:
    """Export endpoint tests"""

    @patch('backend.app.routes.maintenance.ExportService')
    def test_export_returns_excel(self, MockExportService, logged_in_client, mock_mongo):
        mock_service = MockExportService.return_value
        mock_service.export_data.return_value = b'fake_excel_data'
        mock_service.get_export_filename.return_value = 'test.xlsx'

        resp = logged_in_client.post(EXPORT_ENDPOINT, data={})
        assert resp.status_code == 200
        assert resp.content_type in (
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'application/octet-stream',
        )

    @patch('backend.app.routes.maintenance.ExportService')
    def test_export_with_filters(self, MockExportService, logged_in_client, mock_mongo):
        mock_service = MockExportService.return_value
        mock_service.export_data.return_value = b'fake_excel_data'
        mock_service.get_export_filename.return_value = 'test.xlsx'

        logged_in_client.post(EXPORT_ENDPOINT, data={
            'finance_request_number': 'RZ2025',
            'refactoring_status': 'Pending',
        })

        call_args = mock_service.export_data.call_args
        filters = call_args[0][2]  # 3rd positional arg
        assert 'finance_request_number' in filters
        assert filters['refactoring_status'] == 'Pending'

    @patch('backend.app.routes.maintenance.ExportService')
    def test_export_empty_redirects(self, MockExportService, logged_in_client, mock_mongo):
        mock_service = MockExportService.return_value
        mock_service.export_data.return_value = b''

        resp = logged_in_client.post(EXPORT_ENDPOINT, data={})
        assert resp.status_code == 302


class TestFlattenNewFields:
    """新字段清单展平测试"""

    def test_funder_displayed(self, logged_in_client, mock_mongo):
        mock_mongo.refactoring_financing_overview.find.return_value = _mock_chain(
            [MOCK_OVERVIEW_RECORD.copy()]
        )
        mock_mongo.refactoring_financing_overview.count_documents.return_value = 1
        mock_mongo.refactoring_financing_overview.distinct.return_value = []

        resp = logged_in_client.get(ENDPOINT)
        assert b'DB Insurance' in resp.data

    def test_invoice_amount_displayed(self, logged_in_client, mock_mongo):
        mock_mongo.refactoring_financing_overview.find.return_value = _mock_chain(
            [MOCK_OVERVIEW_RECORD.copy()]
        )
        mock_mongo.refactoring_financing_overview.count_documents.return_value = 1
        mock_mongo.refactoring_financing_overview.distinct.return_value = []

        resp = logged_in_client.get(ENDPOINT)
        assert b'2,831.22' in resp.data  # order_details.original_amount

    def test_tenor_display_combines_actual_tenor_and_collection_period(self, logged_in_client, mock_mongo):
        mock_mongo.refactoring_financing_overview.find.return_value = _mock_chain(
            [MOCK_OVERVIEW_RECORD.copy()]
        )
        mock_mongo.refactoring_financing_overview.count_documents.return_value = 1
        mock_mongo.refactoring_financing_overview.distinct.return_value = []

        resp = logged_in_client.get(ENDPOINT)
        assert b'39 + 5' in resp.data

    def test_refactor_id_displayed(self, logged_in_client, mock_mongo):
        mock_mongo.refactoring_financing_overview.find.return_value = _mock_chain(
            [MOCK_OVERVIEW_RECORD.copy()]
        )
        mock_mongo.refactoring_financing_overview.count_documents.return_value = 1
        mock_mongo.refactoring_financing_overview.distinct.return_value = []

        resp = logged_in_client.get(ENDPOINT)
        assert b'GFM2638847' in resp.data

    def test_summary_status_and_batch_not_displayed(self, logged_in_client, mock_mongo):
        mock_mongo.refactoring_financing_overview.find.return_value = _mock_chain(
            [MOCK_OVERVIEW_RECORD.copy()]
        )
        mock_mongo.refactoring_financing_overview.count_documents.return_value = 1
        mock_mongo.refactoring_financing_overview.distinct.return_value = []

        resp = logged_in_client.get(ENDPOINT)
        assert b'Active' not in resp.data  # summary_status 的值不应出现

    def test_filter_by_refactor_id(self, logged_in_client, mock_mongo):
        mock_mongo.refactoring_financing_overview.find.return_value = _mock_chain([])
        mock_mongo.refactoring_financing_overview.count_documents.return_value = 0
        mock_mongo.refactoring_financing_overview.distinct.return_value = []

        logged_in_client.get(f'{ENDPOINT}?refactor_id=GFM2638847')

        call_args = mock_mongo.refactoring_financing_overview.find.call_args
        filters = call_args[0][0]
        assert filters['refactor_id'] == 'GFM2638847'
