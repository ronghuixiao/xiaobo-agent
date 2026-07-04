"""Web Dashboard 测试"""
import pytest


class TestDashboard:
    """Dashboard 测试"""

    def test_dashboard_router_exists(self):
        """测试 Dashboard 路由定义存在"""
        from src.dashboard.app import create_dashboard_router
        router = create_dashboard_router()
        assert router is not None

    def test_dashboard_html_is_valid(self):
        """测试 Dashboard HTML 内容"""
        from src.dashboard.app import DASHBOARD_HTML
        assert "<!DOCTYPE html>" in DASHBOARD_HTML
        assert "小柏 Agent" in DASHBOARD_HTML
        assert "dashboard" in DASHBOARD_HTML.lower()

    def test_dashboard_has_endpoints(self):
        """测试 Dashboard 有正确端点"""
        from src.dashboard.app import create_dashboard_router
        router = create_dashboard_router()
        routes = [r.path for r in router.routes]
        assert "/dashboard" in routes
