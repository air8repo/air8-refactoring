"""额度明细页路由测试（Deal 层重做）"""
from unittest.mock import patch


SAMPLE_DEALS = [
    {'uid': 'U1', 'buyer_code': 'B1', 'buyer_name': 'Buyer One', 'supplier_code': 'S1',
     'supplier_name': 'Seller One', 'currency': 'USD', 'finance_request_number': 'FR1',
     'invoice_number': 'INV1', 'financing_amount': 1000.0, 'earmark_forecast': 1000.0,
     'credit_utilization': 0.0, 'to_be_settled_on_db': None, 'total_os': 1000.0,
     'status': 'eligible', 'status_display': 'eligible', 'finance_status_display': '',
     'settlement_status': '', 'due_date': None, 'actual_funding_date': None, 'batch_number': ''},
    {'uid': 'U1', 'buyer_code': 'B1', 'buyer_name': 'Buyer One', 'supplier_code': 'S1',
     'supplier_name': 'Seller One', 'currency': 'USD', 'finance_request_number': 'FR2',
     'invoice_number': 'INV2', 'financing_amount': 2000.0, 'earmark_forecast': 0.0,
     'credit_utilization': 2000.0, 'to_be_settled_on_db': None, 'total_os': 2000.0,
     'status': 'funded before', 'status_display': 'Funded Successfully',
     'finance_status_display': 'Loan booked', 'settlement_status': 'Pending',
     'due_date': None, 'actual_funding_date': None, 'batch_number': '53'},
]


class TestCreditQueryDetailRoute:

    @patch('backend.app.routes.credit.get_mongo')
    @patch('backend.app.routes.credit.get_pair_deal_rows')
    def test_renders_deal_rows_and_total(self, mock_deals, mock_get_mongo, logged_in_client):
        mock_get_mongo.return_value = object()
        mock_deals.return_value = SAMPLE_DEALS

        resp = logged_in_client.get('/credit/detail?buyer_name=Buyer+One&supplier_name=Seller+One&currency=USD')
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert 'FR1' in body
        assert 'FR2' in body
        assert 'Funded Successfully' in body
        assert '3,000.00' in body  # Total O/S 合计: 1000 + 2000

    @patch('backend.app.routes.credit.get_mongo')
    @patch('backend.app.routes.credit.get_pair_deal_rows')
    def test_total_row_covers_all_pages_not_just_current_page(self, mock_deals, mock_get_mongo, logged_in_client):
        # 生成 25 条 deal（超过每页 20 条），验证合计行用的是全部 25 条而不是当页 20 条
        many_deals = [
            {**SAMPLE_DEALS[0], 'finance_request_number': f'FR{i}', 'earmark_forecast': 100.0,
             'total_os': 100.0, 'credit_utilization': 0.0}
            for i in range(25)
        ]
        mock_get_mongo.return_value = object()
        mock_deals.return_value = many_deals

        resp = logged_in_client.get('/credit/detail?buyer_name=Buyer+One&supplier_name=Seller+One&currency=USD')
        body = resp.get_data(as_text=True)
        assert '2,500.00' in body  # 25 * 100，而不是当页 20 条的 2,000.00

    @patch('backend.app.routes.credit.get_mongo')
    def test_no_mongo_renders_empty_without_crash(self, mock_get_mongo, logged_in_client):
        mock_get_mongo.return_value = None
        resp = logged_in_client.get('/credit/detail')
        assert resp.status_code == 200

    def test_requires_login(self, client):
        resp = client.get('/credit/detail')
        assert resp.status_code in (302, 401)


class TestCreditDetailExportRoute:

    @patch('backend.app.routes.credit.get_mongo')
    @patch('backend.app.routes.credit.get_pair_deal_rows')
    def test_export_returns_xlsx_file(self, mock_deals, mock_get_mongo, logged_in_client):
        mock_get_mongo.return_value = object()
        mock_deals.return_value = SAMPLE_DEALS
        resp = logged_in_client.post('/credit/detail/export', data={
            'buyer_name': 'Buyer One', 'supplier_name': 'Seller One', 'currency': 'USD',
        })
        assert resp.status_code == 200
        assert resp.mimetype == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

    @patch('backend.app.routes.credit.get_mongo')
    @patch('backend.app.routes.credit.get_pair_deal_rows')
    def test_export_empty_result_redirects_with_flash(self, mock_deals, mock_get_mongo, logged_in_client):
        mock_get_mongo.return_value = object()
        mock_deals.return_value = []
        resp = logged_in_client.post('/credit/detail/export', data={
            'buyer_name': 'X', 'supplier_name': 'Y', 'currency': 'USD',
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert '没有找到符合条件的数据' in resp.get_data(as_text=True)

    def test_export_requires_login(self, client):
        resp = client.post('/credit/detail/export')
        assert resp.status_code in (302, 401)
