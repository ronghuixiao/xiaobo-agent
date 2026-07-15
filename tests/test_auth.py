"""API 认证测试"""

import pytest
from unittest.mock import AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient


class TestAPIAuth:
    """Bearer Token 认证测试"""

    def _make_app(self, api_key: str = "test-secret-key"):
        """创建带认证的测试 app"""
        from src.api.routes import create_api_router
        from src.api.auth import create_auth_dependency

        memory = AsyncMock()
        memory.get_stats.return_value = {"conversations": 100}
        tracker = AsyncMock()
        task_mgr = AsyncMock()

        app = FastAPI()
        auth_dep = create_auth_dependency(api_key)
        app.include_router(create_api_router(
            memory=memory,
            tracker=tracker,
            task_mgr=task_mgr,
            dependencies=[auth_dep] if api_key else [],
        ))
        return app

    def test_valid_token_access(self):
        """正确 token 可以访问"""
        app = self._make_app(api_key="my-secret")
        client = TestClient(app)
        resp = client.get("/api/stats", headers={"Authorization": "Bearer my-secret"})
        assert resp.status_code == 200

    def test_invalid_token_rejected(self):
        """错误 token 被拒绝"""
        app = self._make_app(api_key="my-secret")
        client = TestClient(app)
        resp = client.get("/api/stats", headers={"Authorization": "Bearer wrong"})
        assert resp.status_code == 401

    def test_missing_token_rejected(self):
        """没有 token 被拒绝"""
        app = self._make_app(api_key="my-secret")
        client = TestClient(app)
        resp = client.get("/api/stats")
        assert resp.status_code == 401

    def test_no_auth_when_key_empty(self):
        """api_key 为空时不启用认证"""
        from src.api.routes import create_api_router

        memory = AsyncMock()
        memory.get_stats.return_value = {"conversations": 100}

        app = FastAPI()
        app.include_router(create_api_router(memory=memory))
        client = TestClient(app)
        resp = client.get("/api/stats")
        assert resp.status_code == 200

    def test_all_endpoints_require_auth(self):
        """所有端点都需要认证"""
        app = self._make_app(api_key="my-secret")
        client = TestClient(app)
        resp = client.get("/api/health")
        assert resp.status_code == 401
