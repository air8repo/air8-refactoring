"""额度查询页面路由测试（买方层 + 供应商层）"""
from unittest.mock import patch
from unittest.mock import MagicMock


SAMPLE_BUYER_ROWS = [
    {
        'buyer_code': 'B1', 'buyer_name': 'Amazon Services', 'currency': 'USD',
        'celling': 100000.0, 'reserved': 20000.0, 'actual': 75000.0,
        'total_occupied': 95000.0, 'headroom': 5000.0, 'occupancy_rate': 0.95,
        'pairs': [
            {'uid': 'U1', 'buyer_code': 'B1', 'buyer_name': 'Amazon Services',
             'supplier_code': 'S1', 'supplier_name': 'Photonverse Inc', 'currency': 'USD',
             'celling': 100000.0, 'reserved': 20000.0, 'actual': 75000.0,
             'total_occupied': 95000.0, 'headroom': 5000.0, 'occupancy_rate': 0.95},
        ],
    },
]


class TestCreditQueryRoute:

    @patch('backend.app.routes.credit.get_mongo')
    def test_renders_latest_outstanding_actual_and_keeps_warning_threshold(self, mock_get_mongo, logged_in_client):
        mongo = MagicMock()
        mongo.refactoring_onboard_config.find.return_value = [
            {'uid': 'U1', 'refactoring_limit': 100000, 'buyer_code': 'B1',
             'obligor_name': 'Buyer One'},
        ]
        mongo.refactoring_financing_order.find.return_value = [
            {'uid': 'U1', 'buyer_code': 'B1', 'buyer_name': 'Buyer One',
             'finance_request_number': 'FR1', 'invoice_number': 'INV1',
             'financing_amount': 1000, 'status': 'funded before',
             'bank_finance_status': 'Loan booked', 'financing_currency': 'USD'},
        ]
        mongo.refactoring_bank_statement.find.return_value = [
            {'invoice': {'seller_reference': 'INV1', 'creation_time': '2026-09-10T01:00:00Z',
                         'original_amount': 2000},
             'finance': {'advance_ratio_pct': 90, 'status': 'Loan booked',
                         'outstanding_amount': 10}},
            {'invoice': {'seller_reference': 'INV1', 'creation_time': '2026-09-10T02:00:00Z',
                         'original_amount': 2000},
             'finance': {'advance_ratio_pct': 90, 'status': 'Loan booked',
                         'outstanding_amount': 80}},
        ]
        mongo.refactoring_bank_repayment_record.find.return_value = []
        mock_get_mongo.return_value = mongo

        resp = logged_in_client.get('/credit/credit-query')

        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert '80.00' in body
        assert '90%' in body

    @patch('backend.app.routes.credit.get_mongo')
    @patch('backend.app.routes.credit.aggregate_by_buyer')
    @patch('backend.app.routes.credit.get_buyer_supplier_pairs')
    def test_renders_buyer_rows(self, mock_pairs, mock_aggregate, mock_get_mongo, logged_in_client):
        mock_get_mongo.return_value = object()
        mock_pairs.return_value = []
        mock_aggregate.return_value = SAMPLE_BUYER_ROWS

        resp = logged_in_client.get('/credit/credit-query?lang=en')
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert 'Amazon Services' in body
        assert 'Photonverse Inc' in body
        assert 'B1' in body  # Air8 Buyer ID
        assert 'S1' in body  # Air8 Seller ID
        assert 'Earmark Forecast' in body
        assert 'Credit Utilization' in body

    @patch('backend.app.routes.credit.get_mongo')
    @patch('backend.app.routes.credit.aggregate_by_buyer')
    @patch('backend.app.routes.credit.get_buyer_supplier_pairs')
    def test_over_threshold_row_is_highlighted(self, mock_pairs, mock_aggregate, mock_get_mongo, logged_in_client):
        mock_get_mongo.return_value = object()
        mock_pairs.return_value = []
        mock_aggregate.return_value = SAMPLE_BUYER_ROWS

        resp = logged_in_client.get('/credit/credit-query')
        body = resp.get_data(as_text=True)
        assert 'table-danger' in body

    @patch('backend.app.routes.credit.get_mongo')
    @patch('backend.app.routes.credit.aggregate_by_buyer')
    @patch('backend.app.routes.credit.get_buyer_supplier_pairs')
    def test_buyer_row_highlighted_when_diluted_but_a_pair_is_over_threshold(self, mock_pairs, mock_aggregate, mock_get_mongo, logged_in_client):
        # Buyer's own aggregate occupancy (0.5) is under the 0.9 threshold because a
        # low-utilization sibling pair dilutes it, but one individual pair (0.95) is
        # over threshold — the buyer row must still be highlighted so it's discoverable
        # without expanding every row.
        diluted_buyer_rows = [
            {
                'buyer_code': 'B1', 'buyer_name': 'Diluted Buyer', 'currency': 'USD',
                'celling': 200000.0, 'reserved': 0.0, 'actual': 100000.0,
                'total_occupied': 100000.0, 'headroom': 100000.0, 'occupancy_rate': 0.5,
                'pairs': [
                    {'uid': 'U1', 'buyer_code': 'B1', 'buyer_name': 'Diluted Buyer',
                     'supplier_code': 'S1', 'supplier_name': 'Hot Supplier', 'currency': 'USD',
                     'celling': 100000.0, 'reserved': 0.0, 'actual': 95000.0,
                     'total_occupied': 95000.0, 'headroom': 5000.0, 'occupancy_rate': 0.95},
                    {'uid': 'U2', 'buyer_code': 'B1', 'buyer_name': 'Diluted Buyer',
                     'supplier_code': 'S2', 'supplier_name': 'Cool Supplier', 'currency': 'USD',
                     'celling': 100000.0, 'reserved': 0.0, 'actual': 5000.0,
                     'total_occupied': 5000.0, 'headroom': 95000.0, 'occupancy_rate': 0.05},
                ],
            },
        ]
        mock_get_mongo.return_value = object()
        mock_pairs.return_value = []
        mock_aggregate.return_value = diluted_buyer_rows

        resp = logged_in_client.get('/credit/credit-query')
        body = resp.get_data(as_text=True)
        assert body.count('table-danger') == 2  # buyer row + the hot pair row

    @patch('backend.app.routes.credit.get_mongo')
    def test_no_mongo_renders_empty_without_crash(self, mock_get_mongo, logged_in_client):
        mock_get_mongo.return_value = None
        resp = logged_in_client.get('/credit/credit-query')
        assert resp.status_code == 200

    @patch('backend.app.routes.credit.get_mongo')
    @patch('backend.app.routes.credit.aggregate_by_buyer')
    @patch('backend.app.routes.credit.get_buyer_supplier_pairs')
    def test_buyer_filter_passed_to_service(self, mock_pairs, mock_aggregate, mock_get_mongo, logged_in_client):
        mock_get_mongo.return_value = object()
        mock_pairs.return_value = []
        mock_aggregate.return_value = []

        logged_in_client.get('/credit/credit-query?buyer_name=Amazon')
        mock_pairs.assert_called_once()
        assert mock_pairs.call_args[1].get('buyer_filter') == 'Amazon'

    def test_requires_login(self, client):
        resp = client.get('/credit/credit-query')
        assert resp.status_code in (302, 401)
