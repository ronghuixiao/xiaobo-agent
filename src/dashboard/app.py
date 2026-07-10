"""Web Dashboard 路由

提供 Web 界面浏览记忆、情绪、报告等。
"""
import logging
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent / "templates"


def create_dashboard_router() -> APIRouter:
    """创建 Dashboard 路由"""
    router = APIRouter(tags=["dashboard"])

    @router.get("/dashboard", response_class=HTMLResponse)
    async def dashboard():
        """Dashboard 页面"""
        html_path = TEMPLATE_DIR / "dashboard.html"
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))

    return router
