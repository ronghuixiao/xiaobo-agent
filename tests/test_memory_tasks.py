"""MemoryDatabase 任务操作测试"""

import pytest
from datetime import datetime, timedelta


class TestMemoryDatabaseTasks:
    """MemoryDatabase 任务相关方法测试"""

    @pytest.mark.asyncio
    async def test_save_and_get_task(self, memory_db):
        """保存并获取任务"""
        task_id = await memory_db.save_task(
            title="写代码",
            date_str="2026-07-15",
            time_str="10:00",
            task_type="user",
        )
        assert task_id is not None

        tasks = await memory_db.get_tasks_for_date("2026-07-15")
        assert len(tasks) == 1
        assert tasks[0]["title"] == "写代码"
        assert tasks[0]["status"] == "pending"

    @pytest.mark.asyncio
    async def test_get_tasks_by_type(self, memory_db):
        """按类型过滤任务"""
        await memory_db.save_task(title="用户任务", date_str="2026-07-15", task_type="user")
        await memory_db.save_task(title="内置任务", date_str="2026-07-15", task_type="builtin")

        user_tasks = await memory_db.get_tasks_for_date("2026-07-15", task_type="user")
        assert len(user_tasks) == 1
        assert user_tasks[0]["title"] == "用户任务"

    @pytest.mark.asyncio
    async def test_get_today_tasks(self, memory_db):
        """获取今日任务"""
        today = datetime.now().strftime("%Y-%m-%d")
        await memory_db.save_task(title="今日任务", date_str=today)

        tasks = await memory_db.get_today_tasks()
        assert len(tasks) == 1
        assert tasks[0]["title"] == "今日任务"

    @pytest.mark.asyncio
    async def test_update_task_status(self, memory_db):
        """更新任务状态"""
        task_id = await memory_db.save_task(title="写代码", date_str="2026-07-15")
        await memory_db.update_task_status(task_id, "done")

        tasks = await memory_db.get_tasks_for_date("2026-07-15")
        assert tasks[0]["status"] == "done"

    @pytest.mark.asyncio
    async def test_update_task_status_invalid_id(self, memory_db):
        """更新不存在的任务不报错"""
        await memory_db.update_task_status("nonexistent", "done")  # 不应抛异常

    @pytest.mark.asyncio
    async def test_create_task(self, memory_db):
        """创建任务（带自动生成ID）"""
        task_id = await memory_db.create_task(
            title="新任务",
            date_str="2026-07-15",
            time_str="14:00",
            task_type="user",
        )
        assert task_id.startswith("task-")

        tasks = await memory_db.get_tasks_for_date("2026-07-15")
        assert len(tasks) == 1
        assert tasks[0]["title"] == "新任务"
        assert tasks[0]["time"] == "14:00"

    @pytest.mark.asyncio
    async def test_get_all_tasks(self, memory_db):
        """获取所有任务"""
        await memory_db.save_task(title="任务1", date_str="2026-07-14")
        await memory_db.save_task(title="任务2", date_str="2026-07-15")

        all_tasks = await memory_db.get_all_tasks()
        assert len(all_tasks) == 2

    @pytest.mark.asyncio
    async def test_get_pending_tasks_with_time(self, memory_db):
        """获取有时间的待办任务"""
        today = datetime.now().strftime("%Y-%m-%d")
        await memory_db.save_task(title="有时间", date_str=today, time_str="10:00")
        await memory_db.save_task(title="无时间", date_str=today, time_str="")

        pending = await memory_db.get_pending_tasks_with_time(today)
        assert len(pending) == 1
        assert pending[0]["title"] == "有时间"

    @pytest.mark.asyncio
    async def test_mark_done_by_prefix(self, memory_db):
        """按前缀标记任务完成"""
        today = datetime.now().strftime("%Y-%m-%d")
        await memory_db.save_task(title="任务A", date_str=today, task_id="today-001")
        await memory_db.save_task(title="任务B", date_str=today, task_id="today-002")
        await memory_db.save_task(title="其他任务", date_str=today, task_id="other-001")

        await memory_db.mark_done_by_prefix("today-")

        tasks = await memory_db.get_tasks_for_date(today)
        done = [t for t in tasks if t["status"] == "done"]
        assert len(done) == 2

    @pytest.mark.asyncio
    async def test_get_tasks_empty_date(self, memory_db):
        """查询没有任务的日期"""
        tasks = await memory_db.get_tasks_for_date("2099-01-01")
        assert len(tasks) == 0

    @pytest.mark.asyncio
    async def test_task_default_values(self, memory_db):
        """任务默认值"""
        task_id = await memory_db.save_task(title="测试", date_str="2026-07-15")
        tasks = await memory_db.get_tasks_for_date("2026-07-15")
        t = tasks[0]
        assert t["status"] == "pending"
        assert t["time"] == ""
        assert t["type"] == "user"
