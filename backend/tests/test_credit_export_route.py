"""额度管理导出路由测试"""
from unittest.mock import patch


class TestCreditExportRoute:

    @patch('backend.app.routes.credit.get_mongo')
    @patch('backend.app.routes.credit.get_deal_rows')
    @patch('backend.app.routes.credit.aggregate_by_buyer')
    @patch('backend.app.routes.credit.get_buyer_supplier_pairs')
    def test_export_returns_xlsx_file(self, mock_pairs, mock_aggregate, mock_deals, mock_get_mongo, logged_in_client):
        mock_get_mongo.return_value = object()
        mock_pairs.return_value = []
        mock_deals.return_value = []
        mock_aggregate.return_value = [
            {'buyer_code': 'B1', 'buyer_name': 'Amazon Services', 'currency': 'USD',
             'celling': 1000.0, 'reserved': 0.0, 'actual': 0.0, 'total_occupied': 0.0,
             'headroom': 1000.0, 'occupancy_rate': 0.0, 'pairs': []},
        ]
        resp = logged_in_client.post('/credit/export')
        assert resp.status_code == 200
        assert resp.mimetype == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

    @patch('backend.app.routes.credit.get_mongo')
    @patch('backend.app.routes.credit.get_deal_rows')
    @patch('backend.app.routes.credit.aggregate_by_buyer')
    @patch('backend.app.routes.credit.get_buyer_supplier_pairs')
    def test_export_empty_result_redirects_with_flash(self, mock_pairs, mock_aggregate, mock_deals, mock_get_mongo, logged_in_client):
        mock_get_mongo.return_value = object()
        mock_pairs.return_value = []
        mock_deals.return_value = []
        mock_aggregate.return_value = []
        resp = logged_in_client.post('/credit/export', follow_redirects=True)
        assert resp.status_code == 200
        assert '没有找到符合条件的数据' in resp.get_data(as_text=True)

    def test_export_requires_login(self, client):
        resp = client.post('/credit/export')
        assert resp.status_code in (302, 401)

    @patch('backend.app.routes.credit.get_mongo')
    @patch('backend.app.routes.credit.get_deal_rows')
    @patch('backend.app.routes.credit.get_buyer_supplier_pairs')
    def test_export_aggregation_error_redirects_with_flash(self, mock_pairs, mock_deals, mock_get_mongo, logged_in_client):
        mock_get_mongo.return_value = object()
        mock_deals.return_value = []
        mock_pairs.side_effect = RuntimeError('聚合失败：测试异常')
        resp = logged_in_client.post('/credit/export', follow_redirects=True)
        assert resp.status_code == 200
        assert '聚合失败：测试异常' in resp.get_data(as_text=True)
