"""TaskManager 单元测试（使用 MemoryDatabase）"""

import os
import tempfile

import pytest
import pytest_asyncio

from config.settings import Settings, LLMConfig, OllamaConfig, MemoryConfig, CompanionConfig
from src.memory.database import MemoryDatabase


@pytest.fixture
def test_settings(temp_db_path):
    """测试用配置"""
    return Settings(
        llm=LLMConfig(
            provider="ollama",
            ollama=OllamaConfig(
                base_url="http://localhost:11434",
                model="qwen2.5:1.5b",
                embedding_model="nomic-embed-text",
            ),
        ),
        memory=MemoryConfig(db_path=temp_db_path),
        companion=CompanionConfig(
            name="小柏",
            user_name="测试用户",
        ),
    )


@pytest_asyncio.fixture
async def tm(temp_db_path):
    """TaskManager 实例（使用 MemoryDatabase）"""
    from src.companion.task_manager import TaskManager
    db = MemoryDatabase(temp_db_path)
    await db.initialize()
    yield TaskManager(db)
    await db.close()


class TestDetectTaskList:
    """任务列表检测"""

    @pytest.mark.asyncio
    async def test_detect_colon_format(self, tm):
        """检测 '今日任务：A；B；C' 格式"""
        await tm.detect_task_list("今日任务：写代码；复习英语；运动")
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        tasks = await tm.db.get_tasks_for_date(today)
        titles = [t["title"] for t in tasks]
        assert "写代码" in titles
        assert "复习英语" in titles
        assert "运动" in titles

    @pytest.mark.asyncio
    async def test_detect_chinese_comma(self, tm):
        """检测中文逗号分隔"""
        await tm.detect_task_list("任务清单：A、B、C")
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        tasks = await tm.db.get_tasks_for_date(today)
        assert len(tasks) == 3

    @pytest.mark.asyncio
    async def test_detect_english_comma(self, tm):
        """检测英文逗号分隔"""
        await tm.detect_task_list("今天要做：A, B, C")
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        tasks = await tm.db.get_tasks_for_date(today)
        assert len(tasks) == 3

    @pytest.mark.asyncio
    async def test_no_task_list(self, tm):
        """普通消息不触发"""
        await tm.detect_task_list("今天天气真好")
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        tasks = await tm.db.get_tasks_for_date(today)
        assert len(tasks) == 0

    @pytest.mark.asyncio
    async def test_duplicate_detection(self, tm):
        """重复任务不重复添加"""
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        await tm.detect_task_list("今日任务：写代码；复习")
        await tm.detect_task_list("今日任务：写代码；复习")
        tasks = await tm.db.get_tasks_for_date(today)
        assert len(tasks) == 2

    @pytest.mark.asyncio
    async def test_reset_done_tasks(self, tm):
        """已完成任务被重置为 pending"""
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        await tm.detect_task_list("今日任务：写代码")
        tasks = await tm.db.get_tasks_for_date(today)
        await tm.db.update_task_status(tasks[0]["id"], "done")
        await tm.detect_task_list("今日任务：写代码")
        tasks = await tm.db.get_tasks_for_date(today)
        assert tasks[0]["status"] == "pending"


class TestCreateBuiltinTasks:
    """内置任务创建"""

    @pytest.mark.asyncio
    async def test_creates_daily_builtins(self, tm):
        """创建当天的内置任务"""
        await tm.ensure_builtin_tasks()
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        tasks = await tm.db.get_tasks_for_date(today, task_type="builtin")
        titles = [t["title"] for t in tasks]
        assert "早间签到" in titles
        assert "每日日报生成" in titles

    @pytest.mark.asyncio
    async def test_idempotent(self, tm):
        """重复调用不重复创建"""
        await tm.ensure_builtin_tasks()
        await tm.ensure_builtin_tasks()
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        tasks = await tm.db.get_tasks_for_date(today, task_type="builtin")
        assert len(tasks) == 3


class TestMarkTaskDone:
    """任务完成标记"""

    @pytest.mark.asyncio
    async def test_mark_done(self, tm):
        """标记任务完成"""
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        await tm.detect_task_list("今日任务：写代码")
        tasks = await tm.db.get_tasks_for_date(today)
        await tm.update_task_status(tasks[0]["id"], "done")
        updated = await tm.db.get_tasks_for_date(today)
        assert updated[0]["status"] == "done"

    @pytest.mark.asyncio
    async def test_mark_done_invalid_id(self, tm):
        """标记不存在的任务不报错"""
        await tm.update_task_status("nonexistent-id", "done")


class TestGetTasks:
    """任务查询"""

    @pytest.mark.asyncio
    async def test_get_tasks_by_date(self, tm):
        """按日期查询任务"""
        from datetime import datetime, timedelta
        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        await tm.detect_task_list("今日任务：写代码")
        await tm.db.save_task(title="昨天的任务", date_str=yesterday, task_id="old-1")
        today_tasks = await tm.get_tasks_for_date(today)
        assert all(t["date"] == today for t in today_tasks)

    @pytest.mark.asyncio
    async def test_get_today_tasks(self, tm):
        """获取今日任务"""
        await tm.detect_task_list("今日任务：A；B")
        tasks = await tm.get_today_tasks()
        assert len(tasks) == 2
