"""Onboarding 数据定时同步服务测试"""
from datetime import datetime
from unittest.mock import patch, MagicMock, call
import pytest
import requests as req_lib


SAMPLE_API_DATA = [
    {
        'uid': 'UID001',
        'refactoring_funder': 'Funder A',
        'supplier_code': 'S001',
        'supplier_name': 'Seller One',
        'buyer_code': 'B001',
        'buyer_name': 'Buyer One',
        'approved_tenor': '90',
        'advance_ratio': '0.8',
        'refactoring_limit': '1000000',
        'create_time': '2025-01-01 00:00:00',
        'update_time': '2025-06-01 10:00:00',
    },
    {
        'uid': 'UID002',
        'refactoring_funder': 'Funder B',
        'supplier_code': 'S002',
        'supplier_name': 'Seller Two',
        'buyer_code': 'B002',
        'buyer_name': 'Buyer Two',
        'approved_tenor': '',
        'advance_ratio': None,
        'refactoring_limit': '',
        'create_time': '2025-01-02 00:00:00',
        'update_time': '2025-06-02 10:00:00',
    },
    {
        'uid': '',  # missing uid — should be skipped
        'supplier_name': 'Skip Me',
        'update_time': '2025-06-03 10:00:00',
    },
]


# ── _parse_datetime ────────────────────────────────────────────────────────────

class TestParseDatetime:

    def test_parses_datetime_string(self):
        from backend.app.services.onboarding_sync_service import _parse_datetime
        result = _parse_datetime('2025-06-01 10:00:00')
        assert result == datetime(2025, 6, 1, 10, 0, 0)

    def test_parses_iso_format(self):
        from backend.app.services.onboarding_sync_service import _parse_datetime
        result = _parse_datetime('2025-06-01T10:00:00')
        assert result == datetime(2025, 6, 1, 10, 0, 0)

    def test_parses_date_only(self):
        from backend.app.services.onboarding_sync_service import _parse_datetime
        result = _parse_datetime('2025-06-01')
        assert result == datetime(2025, 6, 1)

    def test_returns_datetime_passthrough(self):
        from backend.app.services.onboarding_sync_service import _parse_datetime
        dt = datetime(2025, 1, 1)
        assert _parse_datetime(dt) is dt

    def test_returns_none_for_empty(self):
        from backend.app.services.onboarding_sync_service import _parse_datetime
        assert _parse_datetime('') is None
        assert _parse_datetime(None) is None

    def test_returns_none_for_invalid(self):
        from backend.app.services.onboarding_sync_service import _parse_datetime
        assert _parse_datetime('not-a-date') is None


# ── _map_record ────────────────────────────────────────────────────────────────

class TestMapRecord:

    def test_maps_all_fields(self):
        from backend.app.services.onboarding_sync_service import _map_record
        row = SAMPLE_API_DATA[0]
        rec = _map_record(row)
        assert rec['uid'] == 'UID001'
        assert rec['refactoring_funder'] == 'Funder A'
        assert rec['supplier_code'] == 'S001'
        assert rec['seller_name'] == 'Seller One'
        assert rec['buyer_code'] == 'B001'
        assert rec['obligor_name'] == 'Buyer One'
        assert rec['approved_tenor_days'] == 90
        assert abs(rec['advance_ratio'] - 0.8) < 1e-9
        assert abs(rec['refactoring_limit'] - 1000000) < 1e-9
        assert rec['api_update_time'] == datetime(2025, 6, 1, 10, 0, 0)
        assert 'updated_at' in rec
        assert rec['target_list_status'] == 'Y'  # default when not in API row

    def test_empty_tenor_defaults_to_zero(self):
        from backend.app.services.onboarding_sync_service import _map_record
        rec = _map_record(SAMPLE_API_DATA[1])
        assert rec['approved_tenor_days'] == 0

    def test_null_advance_ratio_is_none(self):
        from backend.app.services.onboarding_sync_service import _map_record
        rec = _map_record(SAMPLE_API_DATA[1])
        assert rec['advance_ratio'] is None

    def test_empty_refactoring_limit_is_none(self):
        from backend.app.services.onboarding_sync_service import _map_record
        rec = _map_record(SAMPLE_API_DATA[1])
        assert rec['refactoring_limit'] is None

    @pytest.mark.parametrize('currency', ['USD', 'EUR'])
    def test_preserves_explicit_credit_limit_currency(self, currency):
        from backend.app.services.onboarding_sync_service import _map_record
        row = {**SAMPLE_API_DATA[0], 'credit_limit_currency': currency,
               'financing_currency': 'USD'}

        rec = _map_record(row)

        assert rec['credit_limit_currency'] == currency
        assert 'financing_currency' not in rec

    def test_defaults_missing_credit_limit_currency_to_usd_without_using_financing_currency(self):
        from backend.app.services.onboarding_sync_service import _map_record
        row = {**SAMPLE_API_DATA[0], 'financing_currency': 'EUR'}

        rec = _map_record(row)

        assert rec['credit_limit_currency'] == 'USD'
        assert 'financing_currency' not in rec

    def test_no_created_at_in_mapped_record(self):
        from backend.app.services.onboarding_sync_service import _map_record
        rec = _map_record(SAMPLE_API_DATA[0])
        assert 'created_at' not in rec


# ── _run_sync ──────────────────────────────────────────────────────────────────

def _make_mongo_mock(meta=None, existing_uid=None):
    mongo = MagicMock()
    mongo.refactoring_sync_meta.find_one.return_value = meta
    if existing_uid:
        mongo.refactoring_onboard_config.find_one.side_effect = (
            lambda q: {'uid': q['uid']} if q.get('uid') == existing_uid else None
        )
    else:
        mongo.refactoring_onboard_config.find_one.return_value = None
    return mongo


class TestRunSync:

    @patch('backend.app.services.onboarding_sync_service._get_mongo')
    @patch('backend.app.services.onboarding_sync_service.requests.get')
    def test_full_sync_inserts_all_valid_records(self, mock_get, mock_get_mongo):
        from backend.app.services.onboarding_sync_service import _run_sync

        mongo = _make_mongo_mock(meta=None)
        mock_get_mongo.return_value = mongo

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = SAMPLE_API_DATA
        mock_get.return_value = mock_resp

        result = _run_sync()
        assert result['inserted'] == 2   # UID001, UID002
        assert result['updated'] == 0
        assert result['skipped'] == 1    # empty uid row
        assert result['total_fetched'] == 3
        assert mongo.refactoring_onboard_config.insert_one.call_count == 2

    @patch('backend.app.services.onboarding_sync_service._get_mongo')
    @patch('backend.app.services.onboarding_sync_service.requests.get')
    def test_incremental_skips_old_records(self, mock_get, mock_get_mongo):
        from backend.app.services.onboarding_sync_service import _run_sync

        # last sync was after UID001's update_time but before UID002's
        meta = {'last_sync_time': datetime(2025, 6, 1, 12, 0, 0)}
        mongo = _make_mongo_mock(meta=meta)
        mock_get_mongo.return_value = mongo

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = SAMPLE_API_DATA
        mock_get.return_value = mock_resp

        result = _run_sync()
        # UID001 update_time 10:00 <= last_sync 12:00 → skipped
        # UID002 update_time next day → inserted
        # empty uid row → skipped
        assert result['inserted'] == 1
        assert result['skipped'] == 2
        assert mongo.refactoring_onboard_config.insert_one.call_count == 1

    @patch('backend.app.services.onboarding_sync_service._get_mongo')
    @patch('backend.app.services.onboarding_sync_service.requests.get')
    def test_updates_existing_record(self, mock_get, mock_get_mongo):
        from backend.app.services.onboarding_sync_service import _run_sync

        mongo = _make_mongo_mock(meta=None, existing_uid='UID001')
        mock_get_mongo.return_value = mongo

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = [SAMPLE_API_DATA[0]]
        mock_get.return_value = mock_resp

        result = _run_sync()
        assert result['updated'] == 1
        assert result['inserted'] == 0
        mongo.refactoring_onboard_config.update_one.assert_called_once()

    @patch('backend.app.services.onboarding_sync_service._get_mongo')
    @patch('backend.app.services.onboarding_sync_service.requests.get')
    def test_updates_sync_meta(self, mock_get, mock_get_mongo):
        from backend.app.services.onboarding_sync_service import _run_sync

        mongo = _make_mongo_mock(meta=None)
        mock_get_mongo.return_value = mongo

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = []
        mock_get.return_value = mongo_resp = mock_resp

        _run_sync()
        mongo.refactoring_sync_meta.update_one.assert_called_once()
        call_args = mongo.refactoring_sync_meta.update_one.call_args
        assert call_args[1].get('upsert') is True
        set_doc = call_args[0][1]['$set']
        assert set_doc['type'] == 'onboarding'
        assert 'last_sync_time' in set_doc

    @patch('backend.app.services.onboarding_sync_service._get_mongo')
    def test_raises_when_no_mongo(self, mock_get_mongo):
        from backend.app.services.onboarding_sync_service import _run_sync
        mock_get_mongo.return_value = None
        with pytest.raises(RuntimeError):
            _run_sync()

    @patch('backend.app.services.onboarding_sync_service._get_mongo')
    @patch('backend.app.services.onboarding_sync_service.requests.get')
    def test_api_failure_raises(self, mock_get, mock_get_mongo):
        from backend.app.services.onboarding_sync_service import _run_sync
        mongo = _make_mongo_mock()
        mock_get_mongo.return_value = mongo
        mock_get.side_effect = req_lib.exceptions.RequestException('timeout')
        with pytest.raises(req_lib.exceptions.RequestException):
            _run_sync()


# ── run_onboarding_sync_manual ─────────────────────────────────────────────────

class TestManualTrigger:

    @patch('backend.app.services.onboarding_sync_service._run_sync')
    def test_returns_success(self, mock_run):
        from backend.app.services.onboarding_sync_service import run_onboarding_sync_manual
        mock_run.return_value = {'inserted': 5, 'updated': 2, 'skipped': 1, 'total_fetched': 8}
        result = run_onboarding_sync_manual()
        assert result['success'] is True
        assert '5' in result['message']
        assert '2' in result['message']

    @patch('backend.app.services.onboarding_sync_service._run_sync')
    def test_returns_failure_on_exception(self, mock_run):
        from backend.app.services.onboarding_sync_service import run_onboarding_sync_manual
        mock_run.side_effect = RuntimeError('DB error')
        result = run_onboarding_sync_manual()
        assert result['success'] is False
        assert 'DB error' in result['message']


# ── HTTP endpoint ──────────────────────────────────────────────────────────────

class TestSyncEndpoint:

    @patch('backend.app.services.onboarding_sync_service.run_onboarding_sync_manual')
    def test_endpoint_returns_200_on_success(self, mock_manual, logged_in_client):
        mock_manual.return_value = {
            'success': True,
            'message': '同步完成：新增 2 条，更新 0 条，跳过 1 条（共拉取 3 条）',
            'details': {'inserted': 2, 'updated': 0, 'skipped': 1, 'total_fetched': 3},
        }
        resp = logged_in_client.post('/maintenance/api/sync-onboarding',
                                     content_type='application/json')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True

    @patch('backend.app.services.onboarding_sync_service.run_onboarding_sync_manual')
    def test_endpoint_returns_500_on_failure(self, mock_manual, logged_in_client):
        mock_manual.return_value = {'success': False, 'message': 'DB error'}
        resp = logged_in_client.post('/maintenance/api/sync-onboarding',
                                     content_type='application/json')
        assert resp.status_code == 500
        data = resp.get_json()
        assert data['success'] is False

    def test_endpoint_requires_login(self, client):
        resp = client.post('/maintenance/api/sync-onboarding',
                           content_type='application/json')
        assert resp.status_code in (302, 401)


# ── scheduler registration ─────────────────────────────────────────────────────

class TestSchedulerRegistration:

    def test_registers_cron_job(self):
        from backend.app.services.onboarding_sync_service import register_onboarding_sync_job
        scheduler = MagicMock()
        app = MagicMock()
        register_onboarding_sync_job(scheduler, app)
        scheduler.add_job.assert_called_once()
        call_kwargs = scheduler.add_job.call_args
        assert call_kwargs[1]['id'] == 'onboarding_sync'
        assert call_kwargs[0][1] == 'cron'
        assert call_kwargs[1]['hour'] == 2
        assert call_kwargs[1]['minute'] == 0
