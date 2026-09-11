"""
冒烟测试 - 回归测试基线
验证所有关键路由的基本可达性，每次迭代必须全部通过。
"""
from unittest.mock import patch, MagicMock


class TestPublicRoutes:
    """测试无需登录即可访问的路由"""

    def test_login_page_loads(self, client):
        """登录页面应该返回 200"""
        resp = client.get('/auth/login')
        assert resp.status_code == 200

    def test_login_page_contains_form(self, client):
        """登录页面应包含登录表单"""
        resp = client.get('/auth/login')
        assert b'login' in resp.data.lower() or b'Login' in resp.data


class TestProtectedRoutes:
    """测试需要登录的路由 - 未登录时应重定向到登录页"""

    def test_dashboard_requires_login(self, client):
        """仪表盘需要登录（/ 重定向到 /dashboard，/dashboard 再重定向到 login）"""
        resp = client.get('/dashboard')
        assert resp.status_code == 302
        assert '/auth/login' in resp.headers.get('Location', '')

    def test_export_requires_login(self, client):
        """数据导出页需要登录"""
        resp = client.get('/export/')
        assert resp.status_code == 302
        assert '/auth/login' in resp.headers.get('Location', '')

    def test_import_requires_login(self, client):
        """数据导入页需要登录"""
        resp = client.get('/import/')
        assert resp.status_code == 302
        assert '/auth/login' in resp.headers.get('Location', '')

    def test_tools_requires_login(self, client):
        """工具页需要登录"""
        resp = client.get('/tools/')
        assert resp.status_code == 302
        assert '/auth/login' in resp.headers.get('Location', '')

    def test_maintenance_requires_login(self, client):
        """数据维护页需要登录"""
        resp = client.get('/maintenance/')
        assert resp.status_code == 302
        assert '/auth/login' in resp.headers.get('Location', '')


class TestAuthenticatedRoutes:
    """测试登录后的路由可达性"""

    def test_root_redirects_to_dashboard(self, logged_in_client):
        """根路由应重定向到 /dashboard"""
        resp = logged_in_client.get('/')
        assert resp.status_code == 302
        assert '/dashboard' in resp.headers.get('Location', '')

    @patch('backend.app.extensions.mongo')
    def test_dashboard_loads(self, mock_mongo, logged_in_client):
        """登录后仪表盘应返回 200（mock MongoDB）"""
        # MagicMock 自动为任何属性访问返回新 MagicMock
        # 只需确保常用方法返回合理值
        for collection_name in ['refactoring_financing_order', 'refactoring_repayment_order',
                                'refactoring_bank_statement', 'refactoring_financing_overview']:
            collection = getattr(mock_mongo, collection_name)
            collection.count_documents.return_value = 0
            collection.find.return_value.sort.return_value.limit.return_value = []
            collection.aggregate.return_value = []
            collection.distinct.return_value = []
        resp = logged_in_client.get('/dashboard')
        assert resp.status_code == 200

    def test_tools_index_loads(self, logged_in_client):
        """登录后工具页应返回 200"""
        resp = logged_in_client.get('/tools/')
        assert resp.status_code == 200

    def test_export_page_loads(self, logged_in_client):
        """登录后导出页应返回 200"""
        resp = logged_in_client.get('/export/')
        assert resp.status_code == 200

    def test_import_page_loads(self, logged_in_client):
        """登录后导入页应返回 200"""
        resp = logged_in_client.get('/import/')
        assert resp.status_code == 200

    def test_maintenance_page_loads(self, logged_in_client):
        """登录后维护页应返回 200"""
        resp = logged_in_client.get('/maintenance/')
        assert resp.status_code == 200
