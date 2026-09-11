import pytest
import sys
import os
from unittest.mock import MagicMock, patch

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))

from backend.app import create_app
from backend.app.config import config_by_name


@pytest.fixture
def app():
    """创建使用 TestingConfig 的 Flask app（数据库: refactoring_test）"""
    app = create_app(config_by_name['test'])
    yield app


@pytest.fixture
def client(app):
    """创建测试客户端"""
    return app.test_client()


@pytest.fixture
def logged_in_client(app):
    """创建已登录的测试客户端（mock Flask-Login）"""
    with app.test_client() as c:
        with patch('flask_login.utils._get_user') as mock_user:
            user = MagicMock()
            user.is_authenticated = True
            user.is_active = True
            user.is_anonymous = False
            user.get_id.return_value = 'test_user_id'
            mock_user.return_value = user
            yield c


@pytest.fixture
def mock_mongo():
    """Mock MongoDB，完全不碰真实数据库"""
    with patch('backend.app.extensions.mongo') as mock:
        yield mock


@pytest.fixture
def mock_requests_get():
    """Mock 所有外部 HTTP GET 请求（n8n API 等）"""
    with patch('requests.get') as mock_get:
        yield mock_get


@pytest.fixture
def mock_onboard_config():
    """创建onboard配置的mock数据"""
    return {
        'uid': 'TESTUID123',
        'target_list_status': 'Y',
        'approved_tenor_days': 30
    }


@pytest.fixture
def mock_financing_order():
    """创建融资订单的mock数据"""
    return {
        'uid': 'TESTUID123',
        'finance_request_number': 'RZ202512110000000094',
        'invoice_number': 'INV123456',
        'due_date': '2025-12-31',
        'target_list_status': 'PENDING',
        'settled_amt_partial': 0.0
    }
