"""
Tools 路由测试 - 外部 API 使用 mock
所有 n8n.air8.cn 的外部 API 调用在测试中通过 mock 替代。
"""
from unittest.mock import patch, MagicMock


class TestCreateDummyInvoicePage:
    """创建 Dummy 发票工具页面测试"""

    def test_page_loads(self, logged_in_client):
        """工具页面应返回 200"""
        resp = logged_in_client.get('/tools/create-dummy-invoice')
        assert resp.status_code == 200

    @patch('backend.app.routes.tools.requests.get')
    def test_create_success(self, mock_get, logged_in_client):
        """提交有效参数应返回成功 JSON"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {'invoiceNumber': 'INV-TEST-001'}
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        resp = logged_in_client.post('/tools/create-dummy-invoice', data={
            'buyer_code': 'C0001795',
            'supplier_code': 'C0001574',
            'amount': '0.01',
        })
        assert resp.status_code == 200
        json_data = resp.get_json()
        assert json_data['success'] is True
        assert json_data['data']['invoiceNumber'] == 'INV-TEST-001'

        # 验证 API 调用参数
        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args
        assert call_kwargs[1]['params']['buyerCode'] == 'C0001795'
        assert call_kwargs[1]['params']['supplierCode'] == 'C0001574'
        assert call_kwargs[1]['params']['amount'] == '0.01'

    def test_create_missing_fields(self, logged_in_client):
        """缺少必填字段应返回失败"""
        resp = logged_in_client.post('/tools/create-dummy-invoice', data={
            'buyer_code': 'C0001795',
            'supplier_code': '',
            'amount': '0.01',
        })
        assert resp.status_code == 200
        json_data = resp.get_json()
        assert json_data['success'] is False

    def test_create_invalid_amount(self, logged_in_client):
        """无效金额应返回失败"""
        resp = logged_in_client.post('/tools/create-dummy-invoice', data={
            'buyer_code': 'C0001795',
            'supplier_code': 'C0001574',
            'amount': 'abc',
        })
        assert resp.status_code == 200
        json_data = resp.get_json()
        assert json_data['success'] is False

    @patch('backend.app.routes.tools.requests.get')
    def test_create_api_error(self, mock_get, logged_in_client):
        """API 调用失败应返回错误信息"""
        import requests as real_requests
        mock_get.side_effect = real_requests.RequestException('Connection refused')

        resp = logged_in_client.post('/tools/create-dummy-invoice', data={
            'buyer_code': 'C0001795',
            'supplier_code': 'C0001574',
            'amount': '0.01',
        })
        assert resp.status_code == 200
        json_data = resp.get_json()
        assert json_data['success'] is False


class TestInvoiceDownloadPage:
    """发票文件下载工具测试"""

    def test_page_loads(self, logged_in_client):
        """下载工具页面应返回 200"""
        resp = logged_in_client.get('/tools/invoice-download')
        assert resp.status_code == 200

    def test_empty_input_redirects(self, logged_in_client):
        """空输入应重定向"""
        resp = logged_in_client.post('/tools/invoice-download', data={
            'financing_nos': '',
        })
        assert resp.status_code == 302

    @patch('backend.app.routes.tools.requests.get')
    def test_download_success(self, mock_get, logged_in_client):
        """有效输入应返回 ZIP 文件"""
        # Mock API 返回发票列表
        api_resp = MagicMock()
        api_resp.status_code = 200
        api_resp.json.return_value = [{
            'invoice_no': 'FP001',
            'financing_no': 'RZ001',
            'download_url': 'https://example.com/file1.pdf',
        }]
        api_resp.raise_for_status.return_value = None

        # Mock 文件下载
        file_resp = MagicMock()
        file_resp.status_code = 200
        file_resp.content = b'%PDF-1.4 fake pdf content'
        file_resp.headers = {'Content-Disposition': 'attachment; filename="invoice.pdf"'}
        file_resp.raise_for_status.return_value = None

        # 第一次调用是 API，第二次是文件下载
        mock_get.side_effect = [api_resp, file_resp]

        resp = logged_in_client.post('/tools/invoice-download', data={
            'financing_nos': 'RZ001',
        })
        assert resp.status_code == 200
        assert resp.content_type == 'application/zip'


class TestToolsHelperFunctions:
    """工具辅助函数测试"""

    def test_sanitize_filename(self):
        """文件名清洗应移除非法字符"""
        from backend.app.routes.tools import _sanitize_filename
        assert _sanitize_filename('file:name?.pdf') == 'file_name_.pdf'
        assert _sanitize_filename('normal.pdf') == 'normal.pdf'

    def test_extract_filename_from_url(self):
        """应从 URL 中提取文件名"""
        from backend.app.routes.tools import _extract_filename_from_url
        result = _extract_filename_from_url('https://example.com/path/invoice.pdf?token=abc')
        assert result == 'invoice.pdf'
