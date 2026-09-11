"""FCB 模块测试 — 客户 CRUD + 导出"""
import json
import io
from unittest.mock import patch, MagicMock
from bson import ObjectId
import pytest


# ── 冒烟测试 ──────────────────────────────

class TestFCBSmokeRoutes:
    """未登录用户应被重定向到登录页"""

    def test_clients_page_redirects(self, client):
        resp = client.get('/fcb/clients')
        assert resp.status_code in (302, 308)

    def test_export_page_redirects(self, client):
        resp = client.get('/fcb/export')
        assert resp.status_code in (302, 308)

    def test_api_clients_redirects(self, client):
        resp = client.get('/fcb/api/clients')
        assert resp.status_code in (302, 308)


# ── 页面加载测试 ──────────────────────────────

class TestFCBPages:
    """已登录用户可以访问 FCB 页面"""

    def test_clients_page_loads(self, logged_in_client):
        resp = logged_in_client.get('/fcb/clients')
        assert resp.status_code == 200

    def test_export_page_loads(self, logged_in_client):
        resp = logged_in_client.get('/fcb/export')
        assert resp.status_code == 200

    def test_clients_page_contains_buyer_air8_code_field(self, logged_in_client):
        resp = logged_in_client.get('/fcb/clients')
        assert b'f_buyer_air8_code' in resp.data


# ── 客户 CRUD API 测试 ──────────────────────────────

class TestFCBClientAPI:

    @patch('backend.app.services.fcb_service._get_collection')
    def test_list_clients(self, mock_col, logged_in_client):
        col = MagicMock()
        mock_col.return_value = col
        col.count_documents.return_value = 1
        col.find.return_value = MagicMock(
            sort=MagicMock(return_value=MagicMock(
                skip=MagicMock(return_value=MagicMock(
                    limit=MagicMock(return_value=[
                        {
                            '_id': ObjectId('507f1f77bcf86cd799439011'),
                            'supplier_code': 'SUP-001',
                            'customer_name': 'Test Client',
                            'client_number': '1837',
                            'customer_city': 'NYC',
                            'customer_state': 'NY',
                        }
                    ])
                ))
            ))
        )

        resp = logged_in_client.get('/fcb/api/clients?page=1&pageSize=20')
        data = json.loads(resp.data)
        assert resp.status_code == 200
        assert data['success'] is True
        assert data['data']['total'] == 1
        assert len(data['data']['list']) == 1
        assert data['data']['list'][0]['supplier_code'] == 'SUP-001'

    @patch('backend.app.services.fcb_service._get_collection')
    def test_get_single_client(self, mock_col, logged_in_client):
        col = MagicMock()
        mock_col.return_value = col
        oid = ObjectId('507f1f77bcf86cd799439011')
        col.find_one.return_value = {
            '_id': oid,
            'supplier_code': 'SUP-001',
            'customer_name': 'Test Client',
        }

        resp = logged_in_client.get(f'/fcb/api/clients/{str(oid)}')
        data = json.loads(resp.data)
        assert resp.status_code == 200
        assert data['success'] is True
        assert data['data']['supplier_code'] == 'SUP-001'

    @patch('backend.app.services.fcb_service._get_collection')
    def test_get_client_not_found(self, mock_col, logged_in_client):
        col = MagicMock()
        mock_col.return_value = col
        col.find_one.return_value = None

        resp = logged_in_client.get('/fcb/api/clients/507f1f77bcf86cd799439011')
        assert resp.status_code == 404

    @patch('backend.app.services.fcb_service._get_collection')
    def test_create_client(self, mock_col, logged_in_client):
        col = MagicMock()
        mock_col.return_value = col
        col.find_one.return_value = None  # no duplicate
        col.insert_one.return_value = MagicMock(inserted_id=ObjectId('507f1f77bcf86cd799439011'))

        resp = logged_in_client.post('/fcb/api/clients',
            data=json.dumps({
                'supplier_code': 'SUP-002',
                'client_number': '1838',
                'customer_name': 'New Client',
            }),
            content_type='application/json'
        )
        data = json.loads(resp.data)
        assert resp.status_code == 201
        assert data['success'] is True

    @patch('backend.app.services.fcb_service._get_collection')
    def test_create_client_duplicate(self, mock_col, logged_in_client):
        col = MagicMock()
        mock_col.return_value = col
        col.find_one.return_value = {'supplier_code': 'SUP-001'}  # duplicate exists

        resp = logged_in_client.post('/fcb/api/clients',
            data=json.dumps({'supplier_code': 'SUP-001', 'customer_name': 'Dup'}),
            content_type='application/json'
        )
        assert resp.status_code == 409
        data = json.loads(resp.data)
        assert 'already exists' in data['message']

    @patch('backend.app.services.fcb_service._get_collection')
    def test_create_client_with_buyer_air8_code(self, mock_col, logged_in_client):
        col = MagicMock()
        mock_col.return_value = col
        col.find_one.return_value = None  # no duplicate
        col.insert_one.return_value = MagicMock(inserted_id=ObjectId('507f1f77bcf86cd799439011'))

        resp = logged_in_client.post('/fcb/api/clients',
            data=json.dumps({
                'supplier_code': 'SUP-003',
                'buyer_air8_code': 'BUYER-A',
                'client_number': '1839',
                'customer_name': 'Client C',
            }),
            content_type='application/json'
        )
        data = json.loads(resp.data)
        assert resp.status_code == 201
        assert data['data']['buyer_air8_code'] == 'BUYER-A'
        # 查重条件应包含 buyer_air8_code，而不是仅 supplier_code
        called_query = col.find_one.call_args[0][0]
        assert called_query == {'supplier_code': 'SUP-003', 'buyer_air8_code': 'BUYER-A'}

    @patch('backend.app.services.fcb_service._get_collection')
    def test_create_client_duplicate_same_supplier_different_buyer_air8_code(self, mock_col, logged_in_client):
        col = MagicMock()
        mock_col.return_value = col
        col.find_one.return_value = None  # 不同 buyer_air8_code，不算重复
        col.insert_one.return_value = MagicMock(inserted_id=ObjectId('507f1f77bcf86cd799439012'))

        resp = logged_in_client.post('/fcb/api/clients',
            data=json.dumps({
                'supplier_code': 'SUP-001',  # 与既有客户相同 supplier_code
                'buyer_air8_code': 'BUYER-B',
                'client_number': '1840',
                'customer_name': 'Client D',
            }),
            content_type='application/json'
        )
        assert resp.status_code == 201

    @patch('backend.app.services.fcb_service._get_collection')
    def test_create_client_duplicate_no_buyer_air8_code_matches_customer_name(self, mock_col, logged_in_client):
        col = MagicMock()
        mock_col.return_value = col
        col.find_one.return_value = {'supplier_code': 'SUP-001', 'customer_name': 'Dup Client'}  # 同名重复

        resp = logged_in_client.post('/fcb/api/clients',
            data=json.dumps({
                'supplier_code': 'SUP-001',
                'customer_name': 'Dup Client',
            }),
            content_type='application/json'
        )
        assert resp.status_code == 409
        called_query = col.find_one.call_args[0][0]
        assert called_query == {'supplier_code': 'SUP-001', 'customer_name': 'Dup Client'}

    @patch('backend.app.services.fcb_service._get_collection')
    def test_update_client(self, mock_col, logged_in_client):
        col = MagicMock()
        mock_col.return_value = col
        oid = ObjectId('507f1f77bcf86cd799439011')
        existing = {
            '_id': oid,
            'supplier_code': 'SUP-001',
            'buyer_air8_code': '',
            'customer_name': 'Old Name',
        }
        col.find_one.side_effect = [existing, None]  # 1) 取现有记录 2) 查重未命中
        col.find_one_and_update.return_value = {
            '_id': oid,
            'supplier_code': 'SUP-001',
            'customer_name': 'Updated',
        }

        resp = logged_in_client.put(f'/fcb/api/clients/{str(oid)}',
            data=json.dumps({'customer_name': 'Updated'}),
            content_type='application/json'
        )
        data = json.loads(resp.data)
        assert resp.status_code == 200
        assert data['success'] is True
        assert data['data']['customer_name'] == 'Updated'

    @patch('backend.app.services.fcb_service._get_collection')
    def test_update_client_persists_stripped_buyer_air8_code(self, mock_col, logged_in_client):
        """PUT 提交带首尾空白的 buyer_air8_code 时，实际写入 $set 的值应已 strip，避免绕过查重"""
        col = MagicMock()
        mock_col.return_value = col
        oid = ObjectId('507f1f77bcf86cd799439011')
        existing = {
            '_id': oid,
            'supplier_code': 'SUP-001',
            'buyer_air8_code': 'BUYER-A',
            'customer_name': 'Old Name',
        }
        col.find_one.side_effect = [existing, None]  # 1) 取现有记录 2) 查重未命中
        col.find_one_and_update.return_value = {
            '_id': oid,
            'supplier_code': 'SUP-001',
            'buyer_air8_code': 'BUYER-A',
            'customer_name': 'Old Name',
        }

        resp = logged_in_client.put(f'/fcb/api/clients/{str(oid)}',
            data=json.dumps({'buyer_air8_code': ' BUYER-A '}),
            content_type='application/json'
        )
        assert resp.status_code == 200
        set_arg = col.find_one_and_update.call_args[0][1]['$set']
        assert set_arg['buyer_air8_code'] == 'BUYER-A'

    @patch('backend.app.services.fcb_service._get_collection')
    def test_update_client_duplicate_conflict(self, mock_col, logged_in_client):
        col = MagicMock()
        mock_col.return_value = col
        oid = ObjectId('507f1f77bcf86cd799439011')
        other_oid = ObjectId('507f1f77bcf86cd799439099')
        existing = {
            '_id': oid,
            'supplier_code': 'SUP-001',
            'buyer_air8_code': '',
            'customer_name': 'Old Name',
        }
        conflict = {'_id': other_oid, 'supplier_code': 'SUP-001', 'customer_name': 'Taken Name'}
        col.find_one.side_effect = [existing, conflict]

        resp = logged_in_client.put(f'/fcb/api/clients/{str(oid)}',
            data=json.dumps({'customer_name': 'Taken Name'}),
            content_type='application/json'
        )
        assert resp.status_code == 409

    @patch('backend.app.services.fcb_service._get_collection')
    def test_update_client_not_found(self, mock_col, logged_in_client):
        col = MagicMock()
        mock_col.return_value = col
        col.find_one.return_value = None  # 现有记录都找不到

        resp = logged_in_client.put('/fcb/api/clients/507f1f77bcf86cd799439011',
            data=json.dumps({'customer_name': 'X'}),
            content_type='application/json'
        )
        assert resp.status_code == 404

    @patch('backend.app.services.fcb_service._get_collection')
    def test_delete_client(self, mock_col, logged_in_client):
        col = MagicMock()
        mock_col.return_value = col
        col.delete_one.return_value = MagicMock(deleted_count=1)

        resp = logged_in_client.delete('/fcb/api/clients/507f1f77bcf86cd799439011')
        data = json.loads(resp.data)
        assert resp.status_code == 200
        assert data['success'] is True


# ── 导出 API 测试 ──────────────────────────────

class TestFCBExportAPI:

    def test_export_no_data(self, logged_in_client):
        resp = logged_in_client.post('/fcb/api/export',
            data=json.dumps({}),
            content_type='application/json'
        )
        assert resp.status_code == 400

    def test_export_no_financing_nos(self, logged_in_client):
        resp = logged_in_client.post('/fcb/api/export',
            data=json.dumps({'financing_nos': []}),
            content_type='application/json'
        )
        assert resp.status_code == 400

    @patch('backend.app.services.fcb_service.requests.get')
    @patch('backend.app.services.fcb_service._get_collection')
    def test_export_single_client_xlsx(self, mock_col, mock_get, logged_in_client):
        # Mock n8n API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = [{
            'data': json.dumps([
                {
                    'supplier_code': 'SUP-001',
                    'buyer_name': 'TEST CLIENT',
                    'invoice_number': 'INV-001',
                    'invoice_amount': '100.00',
                    'invoice_date': '2026-01-01',
                }
            ])
        }]
        mock_get.return_value = mock_response

        # Mock MongoDB
        col = MagicMock()
        mock_col.return_value = col
        col.find.return_value = [
            {
                '_id': ObjectId('507f1f77bcf86cd799439011'),
                'supplier_code': 'SUP-001',
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
        ]

        resp = logged_in_client.post('/fcb/api/export',
            data=json.dumps({'financing_nos': ['FN001']}),
            content_type='application/json'
        )
        assert resp.status_code == 200
        assert 'spreadsheetml' in resp.content_type or 'octet-stream' in resp.content_type

    @patch('backend.app.services.fcb_service.requests.get')
    @patch('backend.app.services.fcb_service._get_collection')
    def test_export_multiple_clients_zip(self, mock_col, mock_get, logged_in_client):
        # Mock n8n API with 2 supplier codes
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = [{
            'data': json.dumps([
                {'supplier_code': 'SUP-001', 'buyer_name': 'Client A', 'invoice_number': 'INV-001', 'invoice_amount': '100', 'invoice_date': '2026-01-01'},
                {'supplier_code': 'SUP-002', 'buyer_name': 'Client B', 'invoice_number': 'INV-002', 'invoice_amount': '200', 'invoice_date': '2026-01-02'},
            ])
        }]
        mock_get.return_value = mock_response

        col = MagicMock()
        mock_col.return_value = col
        col.find.return_value = [
            {'_id': ObjectId(), 'supplier_code': 'SUP-001', 'client_number': '1001', 'customer_name': 'Client A',
             'client_customer_no': '', 'customer_address1': '', 'customer_address2': '', 'customer_city': '',
             'customer_state': '', 'customer_zip': '', 'customer_phone': '', 'client_terms_code': '',
             'client_terms_desc': '', 'customer_store_no': '', 'customer_dept_no': ''},
            {'_id': ObjectId(), 'supplier_code': 'SUP-002', 'client_number': '1002', 'customer_name': 'Client B',
             'client_customer_no': '', 'customer_address1': '', 'customer_address2': '', 'customer_city': '',
             'customer_state': '', 'customer_zip': '', 'customer_phone': '', 'client_terms_code': '',
             'client_terms_desc': '', 'customer_store_no': '', 'customer_dept_no': ''},
        ]

        resp = logged_in_client.post('/fcb/api/export',
            data=json.dumps({'financing_nos': ['FN001', 'FN002']}),
            content_type='application/json'
        )
        assert resp.status_code == 200
        assert 'zip' in resp.content_type or 'octet-stream' in resp.content_type

    @patch('backend.app.services.fcb_service.requests.get')
    def test_export_n8n_api_failure(self, mock_get, logged_in_client):
        import requests as req_lib
        mock_get.side_effect = req_lib.RequestException('Connection refused')

        resp = logged_in_client.post('/fcb/api/export',
            data=json.dumps({'financing_nos': ['FN001']}),
            content_type='application/json'
        )
        assert resp.status_code == 500

    @patch('backend.app.services.fcb_service.requests.get')
    @patch('backend.app.services.fcb_service._get_collection')
    def test_export_same_supplier_code_different_buyers(self, mock_col, mock_get, logged_in_client):
        """同一 supplier_code 下两个不同 buyer 的交易，应各自匹配到正确客户并生成两个文件"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = [{
            'data': json.dumps([
                {'supplier_code': 'SUP-001', 'buyer_code': 'BUYER-A', 'buyer_name': 'Buyer A',
                 'invoice_number': 'INV-001', 'invoice_amount': '100', 'invoice_date': '2026-01-01'},
                {'supplier_code': 'SUP-001', 'buyer_code': 'BUYER-B', 'buyer_name': 'Buyer B',
                 'invoice_number': 'INV-002', 'invoice_amount': '200', 'invoice_date': '2026-01-02'},
            ])
        }]
        mock_get.return_value = mock_response

        col = MagicMock()
        mock_col.return_value = col
        col.find.return_value = [
            {'_id': ObjectId(), 'supplier_code': 'SUP-001', 'buyer_air8_code': 'BUYER-A',
             'client_number': '1001', 'customer_name': 'Client A', 'client_customer_no': '',
             'customer_address1': '', 'customer_address2': '', 'customer_city': '', 'customer_state': '',
             'customer_zip': '', 'customer_phone': '', 'client_terms_code': '', 'client_terms_desc': '',
             'customer_store_no': '', 'customer_dept_no': ''},
            {'_id': ObjectId(), 'supplier_code': 'SUP-001', 'buyer_air8_code': 'BUYER-B',
             'client_number': '1002', 'customer_name': 'Client B', 'client_customer_no': '',
             'customer_address1': '', 'customer_address2': '', 'customer_city': '', 'customer_state': '',
             'customer_zip': '', 'customer_phone': '', 'client_terms_code': '', 'client_terms_desc': '',
             'customer_store_no': '', 'customer_dept_no': ''},
        ]

        resp = logged_in_client.post('/fcb/api/export',
            data=json.dumps({'financing_nos': ['FN001', 'FN002']}),
            content_type='application/json'
        )
        assert resp.status_code == 200
        assert 'zip' in resp.content_type or 'octet-stream' in resp.content_type

    @patch('backend.app.services.fcb_service.requests.get')
    @patch('backend.app.services.fcb_service._get_collection')
    def test_export_partial_unmatched_still_succeeds(self, mock_col, mock_get, logged_in_client):
        """部分交易未匹配到客户时，其余交易仍应正常导出"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = [{
            'data': json.dumps([
                {'supplier_code': 'SUP-001', 'buyer_code': 'BUYER-A', 'buyer_name': 'Buyer A',
                 'invoice_number': 'INV-001', 'invoice_amount': '100', 'invoice_date': '2026-01-01'},
                {'supplier_code': 'SUP-999', 'buyer_code': 'UNKNOWN', 'buyer_name': 'Unknown Buyer',
                 'invoice_number': 'INV-999', 'invoice_amount': '999', 'invoice_date': '2026-01-01'},
            ])
        }]
        mock_get.return_value = mock_response

        col = MagicMock()
        mock_col.return_value = col
        col.find.return_value = [
            {'_id': ObjectId(), 'supplier_code': 'SUP-001', 'buyer_air8_code': 'BUYER-A',
             'client_number': '1001', 'customer_name': 'Client A', 'client_customer_no': '',
             'customer_address1': '', 'customer_address2': '', 'customer_city': '', 'customer_state': '',
             'customer_zip': '', 'customer_phone': '', 'client_terms_code': '', 'client_terms_desc': '',
             'customer_store_no': '', 'customer_dept_no': ''},
        ]

        resp = logged_in_client.post('/fcb/api/export',
            data=json.dumps({'financing_nos': ['FN001', 'FN002']}),
            content_type='application/json'
        )
        assert resp.status_code == 200
        assert 'spreadsheetml' in resp.content_type or 'octet-stream' in resp.content_type

    @patch('backend.app.services.fcb_service.requests.get')
    @patch('backend.app.services.fcb_service._get_collection')
    def test_export_all_unmatched_raises(self, mock_col, mock_get, logged_in_client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = [{
            'data': json.dumps([
                {'supplier_code': 'SUP-999', 'buyer_code': 'UNKNOWN', 'buyer_name': 'Unknown Buyer',
                 'invoice_number': 'INV-999', 'invoice_amount': '999', 'invoice_date': '2026-01-01'},
            ])
        }]
        mock_get.return_value = mock_response

        col = MagicMock()
        mock_col.return_value = col
        col.find.return_value = []

        resp = logged_in_client.post('/fcb/api/export',
            data=json.dumps({'financing_nos': ['FN001']}),
            content_type='application/json'
        )
        assert resp.status_code == 500

    @patch('backend.app.services.fcb_service.requests.get')
    @patch('backend.app.services.fcb_service._get_collection')
    def test_export_ambiguous_transaction_skipped_others_still_exported(self, mock_col, mock_get, logged_in_client):
        """同一 supplier_code 下两个候选记录同名且都未填 buyer_air8_code 时，
        对应交易应判为歧义并被跳过，而其余无歧义交易仍应正常导出，不影响整个导出流程"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = [{
            'data': json.dumps([
                {'supplier_code': 'SUP-001', 'buyer_code': 'BUYER-A', 'buyer_name': 'Buyer A',
                 'invoice_number': 'INV-001', 'invoice_amount': '100', 'invoice_date': '2026-01-01'},
                {'supplier_code': 'SUP-001', 'buyer_code': '', 'buyer_name': 'Ambiguous Name',
                 'invoice_number': 'INV-002', 'invoice_amount': '200', 'invoice_date': '2026-01-02'},
            ])
        }]
        mock_get.return_value = mock_response

        col = MagicMock()
        mock_col.return_value = col
        col.find.return_value = [
            {'_id': ObjectId(), 'supplier_code': 'SUP-001', 'buyer_air8_code': 'BUYER-A',
             'client_number': '1001', 'customer_name': 'Client A', 'client_customer_no': '',
             'customer_address1': '', 'customer_address2': '', 'customer_city': '', 'customer_state': '',
             'customer_zip': '', 'customer_phone': '', 'client_terms_code': '', 'client_terms_desc': '',
             'customer_store_no': '', 'customer_dept_no': ''},
            {'_id': ObjectId(), 'supplier_code': 'SUP-001', 'buyer_air8_code': '',
             'client_number': '2001', 'customer_name': 'Ambiguous Name', 'client_customer_no': '',
             'customer_address1': '', 'customer_address2': '', 'customer_city': '', 'customer_state': '',
             'customer_zip': '', 'customer_phone': '', 'client_terms_code': '', 'client_terms_desc': '',
             'customer_store_no': '', 'customer_dept_no': ''},
            {'_id': ObjectId(), 'supplier_code': 'SUP-001', 'buyer_air8_code': '',
             'client_number': '2002', 'customer_name': 'Ambiguous Name', 'client_customer_no': '',
             'customer_address1': '', 'customer_address2': '', 'customer_city': '', 'customer_state': '',
             'customer_zip': '', 'customer_phone': '', 'client_terms_code': '', 'client_terms_desc': '',
             'customer_store_no': '', 'customer_dept_no': ''},
        ]

        resp = logged_in_client.post('/fcb/api/export',
            data=json.dumps({'financing_nos': ['FN001', 'FN002']}),
            content_type='application/json'
        )
        assert resp.status_code == 200
        assert 'spreadsheetml' in resp.content_type or 'octet-stream' in resp.content_type


# ── Excel 列顺序测试 ──────────────────────────────

class TestFCBExcelColumns:

    def test_excel_column_order(self):
        from backend.app.services.fcb_service import EXCEL_COLUMNS
        assert len(EXCEL_COLUMNS) == 24
        assert EXCEL_COLUMNS[0] == 'Client Number'
        assert EXCEL_COLUMNS[9] == 'Invoice Number'
        assert EXCEL_COLUMNS[23] == 'Tradestyle'

    def test_merge_row_keys(self):
        from backend.app.services.fcb_service import _merge_row, EXCEL_COLUMNS
        client = {'client_number': '1837', 'customer_name': 'Test'}
        txn = {'invoice_number': 'INV-001', 'invoice_amount': 100}
        row = _merge_row(client, txn)
        assert list(row.keys()) == EXCEL_COLUMNS


# ── 客户匹配函数测试 ──────────────────────────────

class TestMatchClientForTransaction:

    def test_matches_by_buyer_air8_code(self):
        from backend.app.services.fcb_service import match_client_for_transaction
        candidates = [
            {'_id': 'c1', 'buyer_air8_code': 'BUYER-A', 'customer_name': 'Name A'},
            {'_id': 'c2', 'buyer_air8_code': 'BUYER-B', 'customer_name': 'Name B'},
        ]
        client, ambiguous = match_client_for_transaction('BUYER-B', 'Name B', candidates)
        assert client['_id'] == 'c2'
        assert ambiguous is False

    def test_buyer_air8_code_mismatch_does_not_fallback_to_name(self):
        from backend.app.services.fcb_service import match_client_for_transaction
        candidates = [
            {'_id': 'c1', 'buyer_air8_code': 'BUYER-A', 'customer_name': 'Name A'},
        ]
        # customer_name 与 buyer_name 相同，但 buyer_air8_code 不等，仍不应命中
        client, ambiguous = match_client_for_transaction('BUYER-X', 'Name A', candidates)
        assert client is None
        assert ambiguous is False

    def test_matches_by_customer_name_when_no_buyer_air8_code(self):
        from backend.app.services.fcb_service import match_client_for_transaction
        candidates = [
            {'_id': 'c1', 'buyer_air8_code': '', 'customer_name': 'Kohl S Inc'},
        ]
        client, ambiguous = match_client_for_transaction('', '  kohl s inc  ', candidates)
        assert client['_id'] == 'c1'
        assert ambiguous is False

    def test_no_match_when_name_differs(self):
        from backend.app.services.fcb_service import match_client_for_transaction
        candidates = [
            {'_id': 'c1', 'buyer_air8_code': '', 'customer_name': 'Kohl S Inc'},
        ]
        client, ambiguous = match_client_for_transaction('', 'Different Buyer', candidates)
        assert client is None
        assert ambiguous is False

    def test_ambiguous_when_multiple_candidates_match(self):
        from backend.app.services.fcb_service import match_client_for_transaction
        candidates = [
            {'_id': 'c1', 'buyer_air8_code': '', 'customer_name': 'Same Name'},
            {'_id': 'c2', 'buyer_air8_code': '', 'customer_name': 'Same Name'},
        ]
        client, ambiguous = match_client_for_transaction('', 'Same Name', candidates)
        assert client is None
        assert ambiguous is True

    def test_no_candidates_returns_unmatched(self):
        from backend.app.services.fcb_service import match_client_for_transaction
        client, ambiguous = match_client_for_transaction('BUYER-A', 'Name A', [])
        assert client is None

    def test_code_match_wins_over_conflicting_name_fallback_match(self):
        """精确 buyer_air8_code 匹配应优先于姓名 fallback 匹配，两者冲突时不应判为歧义"""
        from backend.app.services.fcb_service import match_client_for_transaction
        candidates = [
            # 遗留记录：未填 buyer_air8_code，靠姓名匹配
            {'_id': 'legacy', 'buyer_air8_code': '', 'customer_name': 'Kohl S Inc'},
            # 新记录：同名但填了精确 buyer_air8_code
            {'_id': 'new', 'buyer_air8_code': 'BUYER-A', 'customer_name': 'Kohl S Inc'},
        ]
        client, ambiguous = match_client_for_transaction('BUYER-A', 'Kohl S Inc', candidates)
        assert ambiguous is False
        assert client['_id'] == 'new'
        assert ambiguous is False
