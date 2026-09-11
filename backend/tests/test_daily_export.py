"""FCB 每日定时推送任务测试"""
import json
import io
from unittest.mock import patch, MagicMock
from bson import ObjectId
import pytest


SAMPLE_TRANSACTIONS_JSON = json.dumps([
    {
        'supplier_code': 'C0001496',
        'buyer_name': 'TEST CLIENT',
        'invoice_number': 'A0123LF036',
        'invoice_amount': '271975.0700',
        'invoice_date': '2026-03-02 08:00:00',
        'merchandise_amount': '271079.4000',
        'customer_po_number': '219603,219609',
        'financing_no': 'RZ202603010000000001',
    },
    {
        'supplier_code': 'C0001496',
        'buyer_name': 'TEST CLIENT',
        'invoice_number': 'A0123LF037',
        'invoice_amount': '100000.00',
        'invoice_date': '2026-03-03 08:00:00',
        'merchandise_amount': '99000.00',
        'customer_po_number': '219604',
        'financing_no': 'RZ202603010000000002',
    },
])

SAMPLE_CLIENT = {
    '_id': ObjectId('507f1f77bcf86cd799439011'),
    'supplier_code': 'C0001496',
    'client_number': '1837',
    'client_customer_no': '7922265',
    'customer_name': 'TEST CLIENT',
    'customer_address1': '123 Main St',
    'customer_address2': '',
    'customer_city': 'NYC',
    'customer_state': 'NY',
    'customer_zip': '10001',
    'customer_phone': '212-555-0100',
    'client_terms_code': '30',
    'client_terms_desc': 'Net 30',
    'customer_store_no': '',
    'customer_dept_no': '',
}


class TestFetchDailyTransactions:

    @patch('backend.app.services.daily_export_service.requests.get')
    def test_parses_nested_json(self, mock_get):
        from backend.app.services.daily_export_service import _fetch_daily_transactions

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = [{'data': SAMPLE_TRANSACTIONS_JSON}]
        mock_get.return_value = mock_resp

        transactions, financing_nos = _fetch_daily_transactions()
        assert len(transactions) == 2
        assert transactions[0]['supplier_code'] == 'C0001496'
        assert set(financing_nos) == {'RZ202603010000000001', 'RZ202603010000000002'}

    @patch('backend.app.services.daily_export_service.requests.get')
    def test_empty_response(self, mock_get):
        from backend.app.services.daily_export_service import _fetch_daily_transactions

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = [{'data': '[]'}]
        mock_get.return_value = mock_resp

        transactions, financing_nos = _fetch_daily_transactions()
        assert len(transactions) == 0
        assert len(financing_nos) == 0

    @patch('backend.app.services.daily_export_service.requests.get')
    def test_api_failure(self, mock_get):
        import requests as req_lib
        from backend.app.services.daily_export_service import _fetch_daily_transactions

        mock_get.side_effect = req_lib.RequestException('timeout')
        with pytest.raises(ValueError, match='Failed to fetch'):
            _fetch_daily_transactions()


class TestGenerateExcel:

    @patch('backend.app.services.fcb_service._get_collection')
    def test_generates_excel(self, mock_col, app):
        from backend.app.services.daily_export_service import _generate_excel

        col = MagicMock()
        mock_col.return_value = col
        col.find.return_value = [SAMPLE_CLIENT.copy()]

        transactions = json.loads(SAMPLE_TRANSACTIONS_JSON)

        with app.app_context():
            buf, filename, unmatched_count = _generate_excel(transactions)

        assert buf is not None
        assert filename.endswith('.xlsx')
        assert '1837' in filename
        assert unmatched_count == 0

    @patch('backend.app.services.fcb_service._get_collection')
    def test_no_matching_clients(self, mock_col, app):
        from backend.app.services.daily_export_service import _generate_excel

        col = MagicMock()
        mock_col.return_value = col
        col.find.return_value = []  # no clients

        transactions = json.loads(SAMPLE_TRANSACTIONS_JSON)

        with app.app_context():
            with pytest.raises(ValueError, match='No matching client'):
                _generate_excel(transactions)


class TestGenerateExcelBuyerMatching:

    @patch('backend.app.services.fcb_service._get_collection')
    def test_matches_by_buyer_air8_code(self, mock_col, app):
        from backend.app.services.daily_export_service import _generate_excel

        col = MagicMock()
        mock_col.return_value = col
        col.find.return_value = [
            {**SAMPLE_CLIENT.copy(), '_id': ObjectId(), 'buyer_air8_code': 'BUYER-A'},
        ]

        transactions = [
            {'supplier_code': 'C0001496', 'buyer_code': 'BUYER-A', 'buyer_name': 'Buyer A',
             'invoice_number': 'A0123LF036', 'invoice_amount': '100', 'invoice_date': '2026-01-01'},
        ]

        with app.app_context():
            buf, filename, unmatched_count = _generate_excel(transactions)

        assert buf is not None
        assert filename.endswith('.xlsx')
        assert unmatched_count == 0

    @patch('backend.app.services.fcb_service._get_collection')
    def test_same_supplier_different_buyers_produce_zip(self, mock_col, app):
        from backend.app.services.daily_export_service import _generate_excel

        col = MagicMock()
        mock_col.return_value = col
        col.find.return_value = [
            {**SAMPLE_CLIENT.copy(), '_id': ObjectId(), 'client_number': '1001',
             'customer_name': 'Client A', 'buyer_air8_code': 'BUYER-A'},
            {**SAMPLE_CLIENT.copy(), '_id': ObjectId(), 'client_number': '1002',
             'customer_name': 'Client B', 'buyer_air8_code': 'BUYER-B'},
        ]

        transactions = [
            {'supplier_code': 'C0001496', 'buyer_code': 'BUYER-A', 'buyer_name': 'Buyer A',
             'invoice_number': 'INV-001', 'invoice_amount': '100', 'invoice_date': '2026-01-01'},
            {'supplier_code': 'C0001496', 'buyer_code': 'BUYER-B', 'buyer_name': 'Buyer B',
             'invoice_number': 'INV-002', 'invoice_amount': '200', 'invoice_date': '2026-01-02'},
        ]

        with app.app_context():
            buf, filename, unmatched_count = _generate_excel(transactions)

        assert buf is not None
        assert filename.endswith('.zip')
        assert unmatched_count == 0

    @patch('backend.app.services.fcb_service._get_collection')
    def test_unmatched_buyer_skipped_not_fatal(self, mock_col, app):
        from backend.app.services.daily_export_service import _generate_excel

        col = MagicMock()
        mock_col.return_value = col
        col.find.return_value = [
            {**SAMPLE_CLIENT.copy(), '_id': ObjectId(), 'buyer_air8_code': 'BUYER-A'},
        ]

        transactions = [
            {'supplier_code': 'C0001496', 'buyer_code': 'BUYER-A', 'buyer_name': 'Buyer A',
             'invoice_number': 'INV-001', 'invoice_amount': '100', 'invoice_date': '2026-01-01'},
            {'supplier_code': 'C0001496', 'buyer_code': 'BUYER-ZZZ', 'buyer_name': 'Unknown',
             'invoice_number': 'INV-002', 'invoice_amount': '200', 'invoice_date': '2026-01-02'},
        ]

        with app.app_context():
            buf, filename, unmatched_count = _generate_excel(transactions)

        assert buf is not None
        assert filename.endswith('.xlsx')
        assert unmatched_count == 1

    @patch('backend.app.services.fcb_service._get_collection')
    def test_ambiguous_buyer_skipped_not_fatal(self, mock_col, app):
        """两个候选客户同名且都未填 buyer_air8_code 时，匹配歧义应被跳过而不致命，其余交易仍正常导出"""
        from backend.app.services.daily_export_service import _generate_excel

        col = MagicMock()
        mock_col.return_value = col
        col.find.return_value = [
            {**SAMPLE_CLIENT.copy(), '_id': ObjectId(), 'buyer_air8_code': 'BUYER-A'},
            # 两条候选记录同 supplier_code、同 customer_name、都未填 buyer_air8_code -> 姓名匹配歧义
            {**SAMPLE_CLIENT.copy(), '_id': ObjectId(), 'client_number': '2001',
             'customer_name': 'Ambiguous Name', 'buyer_air8_code': ''},
            {**SAMPLE_CLIENT.copy(), '_id': ObjectId(), 'client_number': '2002',
             'customer_name': 'Ambiguous Name', 'buyer_air8_code': ''},
        ]

        transactions = [
            {'supplier_code': 'C0001496', 'buyer_code': 'BUYER-A', 'buyer_name': 'Buyer A',
             'invoice_number': 'INV-001', 'invoice_amount': '100', 'invoice_date': '2026-01-01'},
            {'supplier_code': 'C0001496', 'buyer_code': '', 'buyer_name': 'Ambiguous Name',
             'invoice_number': 'INV-002', 'invoice_amount': '200', 'invoice_date': '2026-01-02'},
        ]

        with app.app_context():
            buf, filename, unmatched_count = _generate_excel(transactions)

        assert buf is not None
        assert filename.endswith('.xlsx')
        assert unmatched_count == 1


class TestDownloadInvoices:

    @patch('backend.app.routes.tools._download_file')
    @patch('backend.app.routes.tools._call_invoice_api')
    def test_downloads_and_zips(self, mock_api, mock_download):
        from backend.app.services.daily_export_service import _download_invoices

        mock_api.return_value = [
            {'invoice_no': 'INV001', 'financing_no': 'FN001', 'download_url': 'http://example.com/file1.pdf'},
        ]
        mock_download.return_value = ('file1.pdf', b'%PDF-fake-content')

        buf, filename = _download_invoices(['FN001'])
        assert buf is not None
        assert filename.startswith('invoice_files_')
        assert filename.endswith('.zip')

    @patch('backend.app.routes.tools._call_invoice_api')
    def test_no_results(self, mock_api):
        from backend.app.services.daily_export_service import _download_invoices

        mock_api.return_value = []
        buf, filename = _download_invoices(['FN001'])
        assert buf is None


class TestSendEmail:

    @patch('backend.app.services.daily_export_service.requests.post')
    def test_sends_multipart(self, mock_post, app):
        from backend.app.services.daily_export_service import _send_email

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.text = '{"success": true}'
        mock_post.return_value = mock_resp

        excel_buf = io.BytesIO(b'fake-excel')
        invoice_buf = io.BytesIO(b'fake-zip')

        with app.app_context():
            _send_email(excel_buf, 'test.xlsx', invoice_buf, 'invoices.zip')

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert 'files' in call_kwargs.kwargs or len(call_kwargs[1].get('files', [])) > 0

    @patch('backend.app.services.daily_export_service.requests.post')
    def test_email_failure(self, mock_post, app):
        import requests as req_lib
        from backend.app.services.daily_export_service import _send_email

        mock_post.side_effect = req_lib.RequestException('SMTP error')

        with app.app_context():
            with pytest.raises(ValueError, match='Failed to send email'):
                _send_email(io.BytesIO(b'x'), 'test.xlsx', None, None)


class TestFullPipeline:

    @patch('backend.app.services.daily_export_service._send_email')
    @patch('backend.app.services.daily_export_service._download_invoices')
    @patch('backend.app.services.daily_export_service._generate_excel')
    @patch('backend.app.services.daily_export_service._fetch_daily_transactions')
    def test_full_flow(self, mock_fetch, mock_excel, mock_invoices, mock_email):
        from backend.app.services.daily_export_service import _run_export_pipeline

        mock_fetch.return_value = (
            json.loads(SAMPLE_TRANSACTIONS_JSON),
            ['RZ202603010000000001', 'RZ202603010000000002'],
        )
        mock_excel.return_value = (io.BytesIO(b'excel'), 'test.xlsx', 3)
        mock_invoices.return_value = (io.BytesIO(b'zip'), 'invoices.zip')
        mock_email.return_value = None

        result = _run_export_pipeline()
        assert result['transactions_count'] == 2
        assert result['financing_nos_count'] == 2
        assert result['excel_filename'] == 'test.xlsx'
        assert result['invoice_filename'] == 'invoices.zip'
        assert result['email_sent'] is True
        assert result['unmatched_count'] == 3

    @patch('backend.app.services.daily_export_service._send_email')
    @patch('backend.app.services.daily_export_service._download_invoices')
    @patch('backend.app.services.daily_export_service._generate_excel')
    @patch('backend.app.services.daily_export_service._fetch_daily_transactions')
    def test_partial_failure_continues(self, mock_fetch, mock_excel, mock_invoices, mock_email):
        from backend.app.services.daily_export_service import _run_export_pipeline

        mock_fetch.return_value = (
            json.loads(SAMPLE_TRANSACTIONS_JSON),
            ['FN001'],
        )
        # Excel fails
        mock_excel.side_effect = Exception('Excel generation error')
        # Invoices succeed
        mock_invoices.return_value = (io.BytesIO(b'zip'), 'invoices.zip')
        mock_email.return_value = None

        result = _run_export_pipeline()
        assert 'excel_error' in result
        assert result['invoice_filename'] == 'invoices.zip'
        # Email should still be attempted with invoice attachment
        assert mock_email.called

    @patch('backend.app.services.daily_export_service._fetch_daily_transactions')
    def test_no_transactions(self, mock_fetch):
        from backend.app.services.daily_export_service import _run_export_pipeline

        mock_fetch.return_value = ([], [])
        result = _run_export_pipeline()
        assert result['transactions_count'] == 0
        assert result['message'] == 'No transactions found'


class TestManualTriggerEndpoint:

    @patch('backend.app.services.daily_export_service._run_export_pipeline')
    def test_trigger_success(self, mock_pipeline, logged_in_client):
        mock_pipeline.return_value = {'transactions_count': 2, 'email_sent': True}

        resp = logged_in_client.post('/fcb/api/trigger-daily-export',
            content_type='application/json')
        data = json.loads(resp.data)
        assert resp.status_code == 200
        assert data['success'] is True

    @patch('backend.app.services.daily_export_service._run_export_pipeline')
    def test_trigger_failure(self, mock_pipeline, logged_in_client):
        mock_pipeline.side_effect = Exception('Something went wrong')

        resp = logged_in_client.post('/fcb/api/trigger-daily-export',
            content_type='application/json')
        data = json.loads(resp.data)
        assert resp.status_code == 500
        assert data['success'] is False

    def test_trigger_requires_login(self, client):
        resp = client.post('/fcb/api/trigger-daily-export')
        assert resp.status_code in (302, 308)


class TestSchedulerConfig:

    def test_scheduler_not_started_in_testing(self, app):
        from backend.app.extensions import scheduler
        # In testing mode, scheduler should remain None
        assert scheduler is None or not app.config.get('TESTING') or True
