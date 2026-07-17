"""测试待办任务（upcoming）API 能返回所有未来日期的任务"""
import pytest
from datetime import datetime, timedelta


@pytest.mark.asyncio
async def test_upcoming_returns_all_future_tasks(memory_db):
    """upcoming 应返回明天及以后所有 pending 任务，不限于单天"""
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    day_after = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")

    # 创建明天的任务（无 time）
    await memory_db.save_task("明天任务A", tomorrow, task_type="user", task_id="future-001")
    # 创建后天的任务（有 time）
    await memory_db.save_task("后天任务B", day_after, time_str="10:00", task_type="user", task_id="future-002")
    # 创建今天已完成的任务（不应出现在 upcoming）
    today = datetime.now().strftime("%Y-%m-%d")
    await memory_db.save_task("已完成任务", today, task_type="user", task_id="future-done-001")
    await memory_db.update_task_status("future-done-001", "done")

    # 使用 TaskManager 查询
    from src.companion.task_manager import TaskManager
    mgr = TaskManager(memory_db)
    tasks = await mgr.get_upcoming_tasks()

    # 应该返回明天和后天的任务
    ids = {t["id"] for t in tasks}
    assert "future-001" in ids, f"缺少明天任务，got: {ids}"
    assert "future-002" in ids, f"缺少后天任务，got: {ids}"
    # 已完成的不应出现
    assert "future-done-001" not in ids, f"已完成任务不应出现，got: {ids}"


@pytest.mark.asyncio
async def test_upcoming_includes_tasks_without_time(memory_db):
    """upcoming 应包含没有设置 time 字段的任务"""
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    await memory_db.save_task("无时间任务", tomorrow, task_type="user", task_id="notime-001")

    from src.companion.task_manager import TaskManager
    mgr = TaskManager(memory_db)
    tasks = await mgr.get_upcoming_tasks()

    ids = {t["id"] for t in tasks}
    assert "notime-001" in ids, f"无时间任务应出现在 upcoming，got: {ids}"


@pytest.mark.asyncio
async def test_upcoming_empty_when_no_future_tasks(memory_db):
    """没有未来任务时返回空列表"""
    from src.companion.task_manager import TaskManager
    mgr = TaskManager(memory_db)
    tasks = await mgr.get_upcoming_tasks()
    assert tasks == [], f"无未来任务应返回空列表，got: {tasks}"
