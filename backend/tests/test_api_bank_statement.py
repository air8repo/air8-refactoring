"""
Tests for POST /api/bank-statement endpoint, focused on the two raw bank
fields the external consumer needs: Settlement Status and Settlement Date.

These two fields must be the untampered raw bank (DB) values:
  - invoice.settlement_status   (新增 raw 字段)
  - invoice.raw_settlement_date (新增 raw 字段，空值保持为 None，不填 datetime.now())
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime


API_TOKEN = '7a12ef54-12f2-11f1-ba0a-06df603a9138'
ENDPOINT = '/api/bank-statement'


def _mock_mongo_returning(docs):
    """构造一个 _get_mongo mock，使 find().skip().limit() 返回 docs。"""
    mock_mongo = MagicMock()
    mock_mongo.refactoring_bank_statement.count_documents.return_value = len(docs)
    cursor = MagicMock()
    cursor.skip.return_value = cursor
    cursor.limit.return_value = docs
    mock_mongo.refactoring_bank_statement.find.return_value = cursor
    return mock_mongo


class TestBankStatementSettlementFields:

    def test_outputs_settlement_status_and_date(self, client):
        """接口应输出原始的结清状态和结清日期。"""
        doc = {
            'bank_channel': 'DB',
            'parties': {},
            'invoice': {
                'system_invoice_id': 'INV-1',
                'settlement_status': 'Settled',
                'raw_settlement_date': datetime(2026, 5, 1),
            },
            'finance': {},
            'usd_details': {},
        }
        with patch('backend.app.routes.api._get_mongo',
                   return_value=_mock_mongo_returning([doc])):
            resp = client.post(ENDPOINT, headers={'X-API-Token': API_TOKEN}, json={})

        assert resp.status_code == 200
        rec = resp.get_json()['data'][0]
        assert rec['settlement_status'] == 'Settled'
        assert rec['settlement_date'] == datetime(2026, 5, 1).isoformat()

    def test_unsettled_invoice_keeps_blank_date(self, client):
        """未结清发票的结清日期应为空（None），不应被篡改为今天。"""
        doc = {
            'bank_channel': 'DB',
            'parties': {},
            'invoice': {
                'system_invoice_id': 'INV-2',
                'settlement_status': '',
                'raw_settlement_date': None,
            },
            'finance': {},
            'usd_details': {},
        }
        with patch('backend.app.routes.api._get_mongo',
                   return_value=_mock_mongo_returning([doc])):
            resp = client.post(ENDPOINT, headers={'X-API-Token': API_TOKEN}, json={})

        assert resp.status_code == 200
        rec = resp.get_json()['data'][0]
        assert rec['settlement_status'] == ''
        assert rec['settlement_date'] is None
