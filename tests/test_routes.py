"""API 路由测试"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    """创建测试用 FastAPI app"""
    from src.api.routes import create_api_router

    # Mock 依赖
    memory = AsyncMock()
    memory.get_stats.return_value = {"conversations": 100, "facts": 5}

    tracker = AsyncMock()
    tracker.get_emotion_summary.return_value = "情绪摘要"

    task_mgr = MagicMock()
    task_mgr.get_tasks_for_date.return_value = [
        {"id": "t1", "title": "写代码", "date": "2026-07-15", "status": "pending"}
    ]
    task_mgr.get_all_tasks.return_value = [
        {"id": "t1", "title": "写代码", "date": "2026-07-15", "status": "pending"}
    ]
    task_mgr.get_today_tasks.return_value = [
        {"id": "t1", "title": "写代码", "date": "2026-07-15", "status": "pending"}
    ]
    task_mgr.create_task.return_value = "task-new123"
    task_mgr.get_pending_tasks_with_time.return_value = []

    app = FastAPI()
    app.include_router(create_api_router(
        memory=memory,
        tracker=tracker,
        task_mgr=task_mgr,
    ))
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "timestamp" in data


class TestStatsEndpoint:
    def test_stats_returns_data(self, client):
        resp = client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["conversations"] == 100


class TestEmotionEndpoint:
    def test_emotion_summary(self, client):
        resp = client.get("/api/emotions/summary")
        assert resp.status_code == 200


class TestTasksEndpoint:
    def test_get_tasks(self, client):
        resp = client.get("/api/tasks")
        assert resp.status_code == 200
        assert "tasks" in resp.json()

    def test_get_tasks_by_date(self, client):
        resp = client.get("/api/tasks?date=2026-07-15")
        assert resp.status_code == 200

    def test_get_today_tasks(self, client):
        resp = client.get("/api/tasks/today")
        assert resp.status_code == 200
        data = resp.json()
        assert "date" in data
        assert "tasks" in data

    def test_create_task(self, client):
        resp = client.post("/api/tasks?title=新任务&date=2026-07-15")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "created"
        assert "id" in data

    def test_update_task_status(self, client):
        resp = client.put("/api/tasks/t1/status?status=done")
        assert resp.status_code == 200
        assert resp.json()["status"] == "updated"

    def test_get_upcoming_tasks(self, client):
        resp = client.get("/api/tasks/upcoming")
        assert resp.status_code == 200
        assert "tasks" in resp.json()


class TestRootEndpoint:
    def test_root(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "小柏 Agent"
