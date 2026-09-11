"""
Tests for GET /api/onboard-config/active endpoint.
Returns onboarding records where target_list_status = 'Y'.
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime


API_TOKEN = '7a12ef54-12f2-11f1-ba0a-06df603a9138'
ENDPOINT = '/api/onboard-config/active'


class TestOnboardConfigActive:

    def test_no_token_returns_401(self, client):
        """无 token 应返回 401"""
        resp = client.get(ENDPOINT)
        assert resp.status_code == 401
        data = resp.get_json()
        assert data['success'] is False

    def test_wrong_token_returns_401(self, client):
        """错误 token 应返回 401"""
        resp = client.get(ENDPOINT, headers={'X-API-Token': 'bad-token'})
        assert resp.status_code == 401

    def test_returns_only_active_records(self, client):
        """只返回 target_list_status='Y' 的记录"""
        mock_records = [
            {'uid': 'A', 'air8_buyer_id': 'B1', 'obligor_name': 'O1',
             'country': 'CN', 'air8_seller_id': 'S1', 'seller_name': 'Seller1',
             'target_list_status': 'Y', 'approved_tenor_days': 30,
             'max_invoice_count': 10, 'remarks': '', 'first_submit_date': '2025-01-01',
             'created_at': datetime(2025, 1, 1), 'updated_at': datetime(2025, 1, 2)},
        ]

        with patch('backend.app.routes.api._get_mongo') as mock_get_mongo:
            mock_mongo = MagicMock()
            mock_cursor = MagicMock()
            mock_mongo.refactoring_onboard_config.find.return_value = mock_cursor
            mock_cursor.__iter__ = lambda self: iter(mock_records)
            mock_get_mongo.return_value = mock_mongo

            resp = client.get(ENDPOINT, headers={'X-API-Token': API_TOKEN})

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['total'] == 1
        assert data['data'][0]['uid'] == 'A'
        assert data['data'][0]['target_list_status'] == 'Y'

        # Verify the query filter was correct
        mock_mongo.refactoring_onboard_config.find.assert_called_once_with(
            {'target_list_status': 'Y'}, {'_id': 0}
        )

    def test_returns_empty_when_no_active(self, client):
        """无匹配记录时返回空列表"""
        with patch('backend.app.routes.api._get_mongo') as mock_get_mongo:
            mock_mongo = MagicMock()
            mock_cursor = MagicMock()
            mock_mongo.refactoring_onboard_config.find.return_value = mock_cursor
            mock_cursor.__iter__ = lambda self: iter([])
            mock_get_mongo.return_value = mock_mongo

            resp = client.get(ENDPOINT, headers={'X-API-Token': API_TOKEN})

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['total'] == 0
        assert data['data'] == []

    def test_token_via_query_param(self, client):
        """支持通过 query param 传 token"""
        with patch('backend.app.routes.api._get_mongo') as mock_get_mongo:
            mock_mongo = MagicMock()
            mock_cursor = MagicMock()
            mock_mongo.refactoring_onboard_config.find.return_value = mock_cursor
            mock_cursor.__iter__ = lambda self: iter([])
            mock_get_mongo.return_value = mock_mongo

            resp = client.get(f'{ENDPOINT}?token={API_TOKEN}')

        assert resp.status_code == 200

    def test_db_not_connected_returns_500(self, client):
        """数据库未连接返回 500"""
        with patch('backend.app.routes.api._get_mongo', return_value=None):
            resp = client.get(ENDPOINT, headers={'X-API-Token': API_TOKEN})

        assert resp.status_code == 500
        data = resp.get_json()
        assert data['success'] is False
