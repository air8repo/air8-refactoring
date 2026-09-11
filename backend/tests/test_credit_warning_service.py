"""每日额度预警服务测试"""
from unittest.mock import patch, MagicMock
import pytest
import requests as req_lib


WARNED_BUYERS = [
    {'buyer_code': 'B1', 'buyer_name': 'Amazon Services', 'currency': 'USD',
     'celling': 100000.0, 'reserved': 20000.0, 'actual': 75000.0,
     'total_occupied': 95000.0, 'headroom': 5000.0, 'occupancy_rate': 0.95},
]
WARNED_PAIRS = [
    {'uid': 'U1', 'buyer_name': 'Amazon Services', 'supplier_name': 'Photonverse Inc',
     'currency': 'USD', 'celling': 100000.0, 'reserved': 20000.0, 'actual': 75000.0,
     'total_occupied': 95000.0, 'headroom': 5000.0, 'occupancy_rate': 0.95},
]


class TestRunWarningCheck:

    @patch('backend.app.services.credit_warning_service._get_mongo')
    @patch('backend.app.services.credit_warning_service.get_buyer_supplier_pairs')
    @patch('backend.app.services.credit_warning_service.aggregate_by_buyer')
    @patch('backend.app.services.credit_warning_service.check_warnings')
    @patch('backend.app.services.credit_warning_service._send_warning_email')
    def test_sends_email_when_warnings_found(self, mock_send, mock_check, mock_agg, mock_pairs, mock_get_mongo, app):
        from backend.app.services.credit_warning_service import _run_warning_check
        mock_get_mongo.return_value = MagicMock()
        mock_pairs.return_value = WARNED_PAIRS
        mock_agg.return_value = WARNED_BUYERS
        mock_check.return_value = {'buyers': WARNED_BUYERS, 'pairs': WARNED_PAIRS}
        mock_send.return_value = True

        with app.app_context():
            result = _run_warning_check()

        assert result['warned_count'] == 2
        assert result['warned_buyer_count'] == 1
        assert result['warned_pair_count'] == 1
        assert result['email_sent'] is True
        mock_send.assert_called_once()

    @patch('backend.app.services.credit_warning_service._get_mongo')
    @patch('backend.app.services.credit_warning_service.get_buyer_supplier_pairs')
    @patch('backend.app.services.credit_warning_service.aggregate_by_buyer')
    @patch('backend.app.services.credit_warning_service.check_warnings')
    @patch('backend.app.services.credit_warning_service._send_warning_email')
    def test_sends_email_when_only_pairs_warned_buyers_diluted(self, mock_send, mock_check, mock_agg, mock_pairs, mock_get_mongo, app):
        from backend.app.services.credit_warning_service import _run_warning_check
        mock_get_mongo.return_value = MagicMock()
        mock_pairs.return_value = WARNED_PAIRS
        mock_agg.return_value = []  # no buyer-level warnings, e.g. diluted by sibling pairs
        mock_check.return_value = {'buyers': [], 'pairs': WARNED_PAIRS}
        mock_send.return_value = True

        with app.app_context():
            result = _run_warning_check()

        assert result['warned_count'] == 1
        assert result['warned_buyer_count'] == 0
        assert result['warned_pair_count'] == 1
        assert result['email_sent'] is True
        mock_send.assert_called_once()

    @patch('backend.app.services.credit_warning_service._get_mongo')
    @patch('backend.app.services.credit_warning_service.get_buyer_supplier_pairs')
    @patch('backend.app.services.credit_warning_service.aggregate_by_buyer')
    @patch('backend.app.services.credit_warning_service.check_warnings')
    @patch('backend.app.services.credit_warning_service._send_warning_email')
    def test_skips_email_when_no_warnings(self, mock_send, mock_check, mock_agg, mock_pairs, mock_get_mongo, app):
        from backend.app.services.credit_warning_service import _run_warning_check
        mock_get_mongo.return_value = MagicMock()
        mock_pairs.return_value = []
        mock_agg.return_value = []
        mock_check.return_value = {'buyers': [], 'pairs': []}

        with app.app_context():
            result = _run_warning_check()

        assert result['warned_count'] == 0
        assert result['email_sent'] is False
        mock_send.assert_not_called()

    @patch('backend.app.services.credit_warning_service._get_mongo')
    def test_raises_when_no_mongo(self, mock_get_mongo, app):
        from backend.app.services.credit_warning_service import _run_warning_check
        mock_get_mongo.return_value = None
        with app.app_context():
            with pytest.raises(RuntimeError):
                _run_warning_check()


class TestSendWarningEmail:

    def test_posts_json_payload_to_common_email_url(self, app):
        from backend.app.services.credit_warning_service import _send_warning_email
        with app.app_context():
            app.config['COMMON_EMAIL_URL'] = 'https://n8n-v2.air8.cn/webhook/commonSendEmailForRefactoring'
            with patch('backend.app.services.credit_warning_service.requests.post') as mock_post:
                mock_post.return_value = MagicMock(status_code=200, text='ok')
                result = _send_warning_email(WARNED_BUYERS, WARNED_PAIRS)
        assert result is True
        call_kwargs = mock_post.call_args
        payload = call_kwargs[1]['json']
        assert payload['type'] == 'common'
        assert 'Amazon Services' in payload['body']

    def test_returns_false_when_email_url_not_configured(self, app):
        from backend.app.services.credit_warning_service import _send_warning_email
        with app.app_context():
            app.config['COMMON_EMAIL_URL'] = None
            result = _send_warning_email(WARNED_BUYERS, WARNED_PAIRS)
        assert result is False

    def test_raises_on_request_exception(self, app):
        from backend.app.services.credit_warning_service import _send_warning_email
        with app.app_context():
            app.config['COMMON_EMAIL_URL'] = 'https://n8n-v2.air8.cn/webhook/commonSendEmailForRefactoring'
            with patch('backend.app.services.credit_warning_service.requests.post') as mock_post:
                mock_post.side_effect = req_lib.exceptions.RequestException('timeout')
                with pytest.raises(req_lib.exceptions.RequestException):
                    _send_warning_email(WARNED_BUYERS, WARNED_PAIRS)


class TestManualTrigger:

    @patch('backend.app.services.credit_warning_service._run_warning_check')
    def test_returns_success(self, mock_run):
        from backend.app.services.credit_warning_service import run_warning_check_manual
        mock_run.return_value = {'checked_buyers': 3, 'checked_pairs': 5, 'warned_count': 1, 'email_sent': True}
        result = run_warning_check_manual()
        assert result['success'] is True

    @patch('backend.app.services.credit_warning_service._run_warning_check')
    def test_returns_failure_on_exception(self, mock_run):
        from backend.app.services.credit_warning_service import run_warning_check_manual
        mock_run.side_effect = RuntimeError('DB error')
        result = run_warning_check_manual()
        assert result['success'] is False
        assert 'DB error' in result['message']


class TestSchedulerRegistration:

    def test_registers_cron_job_at_seven_am(self):
        from backend.app.services.credit_warning_service import register_credit_warning_job
        scheduler = MagicMock()
        app = MagicMock()
        register_credit_warning_job(scheduler, app)
        scheduler.add_job.assert_called_once()
        call_kwargs = scheduler.add_job.call_args
        assert call_kwargs[1]['id'] == 'credit_limit_warning'
        assert call_kwargs[0][1] == 'cron'
        assert call_kwargs[1]['hour'] == 7
        assert call_kwargs[1]['minute'] == 0


class TestTriggerWarningCheckEndpoint:

    @patch('backend.app.services.credit_warning_service.run_warning_check_manual')
    def test_endpoint_returns_200_on_success(self, mock_manual, logged_in_client):
        mock_manual.return_value = {'success': True, 'checked_buyers': 2, 'checked_pairs': 3,
                                     'warned_count': 0, 'email_sent': False}
        resp = logged_in_client.post('/credit/api/trigger-warning-check')
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True

    @patch('backend.app.services.credit_warning_service.run_warning_check_manual')
    def test_endpoint_returns_500_on_failure(self, mock_manual, logged_in_client):
        mock_manual.return_value = {'success': False, 'message': 'DB error'}
        resp = logged_in_client.post('/credit/api/trigger-warning-check')
        assert resp.status_code == 500

    def test_endpoint_requires_login(self, client):
        resp = client.post('/credit/api/trigger-warning-check')
        assert resp.status_code in (302, 401)


class TestExtensionsRegistersCreditWarningJob:

    def test_extensions_wires_credit_warning_job(self):
        import inspect
        from backend.app.extensions import init_extensions
        source = inspect.getsource(init_extensions)
        assert 'register_credit_warning_job' in source
