"""Web Dashboard 测试"""
import pytest
from pathlib import Path


TEMPLATE_DIR = Path(__file__).parent.parent / "src" / "dashboard" / "templates"


class TestDashboard:
    """Dashboard 测试"""

    def test_dashboard_router_exists(self):
        """测试 Dashboard 路由定义存在"""
        from src.dashboard.app import create_dashboard_router
        router = create_dashboard_router()
        assert router is not None

    def test_dashboard_html_is_valid(self):
        """测试 Dashboard HTML 模板内容"""
        html_path = TEMPLATE_DIR / "dashboard.html"
        assert html_path.exists(), f"模板文件不存在: {html_path}"
        html = html_path.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in html
        assert "小柏 Agent" in html
        assert "dashboard" in html.lower()

    def test_dashboard_has_endpoints(self):
        """测试 Dashboard 有正确端点"""
        from src.dashboard.app import create_dashboard_router
        router = create_dashboard_router()
        routes = [r.path for r in router.routes]
        assert "/dashboard" in routes
