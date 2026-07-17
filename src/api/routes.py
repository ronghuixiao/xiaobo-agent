"""API 路由定义

提供统一的 API 路由，供 main.py include。
使用工厂函数注入依赖（memory, tracker, task_mgr）。
"""

from datetime import datetime, timedelta

from fastapi import APIRouter


def create_api_router(
    memory=None,
    tracker=None,
    task_mgr=None,
    dependencies=None,
) -> APIRouter:
    """创建 API 路由

    Args:
        memory: MemoryDatabase 实例
        tracker: EmotionTracker 实例
        task_mgr: TaskManager 实例
        dependencies: FastAPI 依赖列表（如认证）
    """
    router = APIRouter(tags=["api"], dependencies=dependencies or [])

    # === 根路径 ===

    @router.get("/")
    async def root():
        return {"name": "小柏 Agent", "version": "0.3.0", "status": "running"}

    # === 健康检查 ===

    @router.get("/api/health")
    async def health_check():
        """健康检查端点"""
        return {"status": "ok", "timestamp": datetime.now().isoformat()}

    # === 统计 ===

    @router.get("/api/stats")
    async def get_stats():
        return await memory.get_stats()

    # === 情绪 ===

    @router.get("/api/emotions/summary")
    async def get_emotion_summary(days: int = 7):
        return await tracker.get_emotion_summary(days)

    # === 任务 ===

    @router.get("/api/tasks")
    async def get_tasks(date: str = ""):
        if date:
            tasks = await task_mgr.get_tasks_for_date(date)
        else:
            tasks = await task_mgr.get_all_tasks()
        return {"tasks": tasks}

    @router.get("/api/tasks/today")
    async def get_today_tasks():
        today = datetime.now().strftime("%Y-%m-%d")
        return {"date": today, "tasks": await task_mgr.get_today_tasks()}

    @router.post("/api/tasks")
    async def create_task(title: str = "", date: str = "", time: str = "", task_type: str = "user"):
        task_id = await task_mgr.create_task(title, date, time, task_type)
        return {"id": task_id, "status": "created"}

    @router.put("/api/tasks/{task_id}/status")
    async def update_task_status(task_id: str, status: str = "done"):
        await task_mgr.update_task_status(task_id, status)
        return {"status": "updated"}

    @router.get("/api/tasks/upcoming")
    async def get_upcoming_tasks():
        return {"tasks": await task_mgr.get_upcoming_tasks()}

    @router.post("/api/tasks/move")
    async def move_tasks(from_date: str = "", to_date: str = ""):
        """将待办任务从一个日期移动到另一个日期"""
        if not from_date or not to_date:
            return {"error": "需要 from_date 和 to_date 参数"}
        count = await task_mgr.move_pending_tasks(from_date, to_date)
        return {"moved": count, "from": from_date, "to": to_date}

    return router
