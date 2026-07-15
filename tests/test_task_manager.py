"""TaskManager 单元测试"""

import os
import tempfile
import sqlite3
from datetime import datetime, timedelta

import pytest


@pytest.fixture
def temp_db():
    """临时数据库，含 tasks 表"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_tasks.db")
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                date TEXT NOT NULL,
                time TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                type TEXT DEFAULT 'user',
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()
        yield db_path


@pytest.fixture
def tm(temp_db):
    """TaskManager 实例"""
    from src.companion.task_manager import TaskManager
    return TaskManager(db_path=temp_db)


class TestDetectTaskList:
    """任务列表检测"""

    def test_detect_colon_format(self, tm):
        """检测 '今日任务：A；B；C' 格式"""
        tm.detect_task_list("今日任务：写代码；复习英语；运动")
        tasks = tm.get_tasks_for_date(datetime.now().strftime("%Y-%m-%d"))
        titles = [t["title"] for t in tasks]
        assert "写代码" in titles
        assert "复习英语" in titles
        assert "运动" in titles

    def test_detect_chinese_comma(self, tm):
        """检测中文逗号分隔"""
        tm.detect_task_list("任务清单：A、B、C")
        tasks = tm.get_tasks_for_date(datetime.now().strftime("%Y-%m-%d"))
        assert len(tasks) == 3

    def test_detect_english_comma(self, tm):
        """检测英文逗号分隔"""
        tm.detect_task_list("今天要做：A, B, C")
        tasks = tm.get_tasks_for_date(datetime.now().strftime("%Y-%m-%d"))
        assert len(tasks) == 3

    def test_no_task_list(self, tm):
        """普通消息不触发"""
        tm.detect_task_list("今天天气真好")
        tasks = tm.get_tasks_for_date(datetime.now().strftime("%Y-%m-%d"))
        assert len(tasks) == 0

    def test_duplicate_detection(self, tm):
        """重复任务不重复添加"""
        today = datetime.now().strftime("%Y-%m-%d")
        tm.detect_task_list("今日任务：写代码；复习")
        tm.detect_task_list("今日任务：写代码；复习")
        tasks = tm.get_tasks_for_date(today)
        assert len(tasks) == 2  # 不应变成4个

    def test_reset_done_tasks(self, tm):
        """已完成任务被重置为 pending"""
        today = datetime.now().strftime("%Y-%m-%d")
        tm.detect_task_list("今日任务：写代码")
        # 手动标记为 done
        tasks = tm.get_tasks_for_date(today)
        tm.update_task_status(tasks[0]["id"], "done")
        # 重新提供清单
        tm.detect_task_list("今日任务：写代码")
        tasks = tm.get_tasks_for_date(today)
        assert tasks[0]["status"] == "pending"


class TestCreateBuiltinTasks:
    """内置任务创建"""

    def test_creates_daily_builtins(self, tm):
        """创建当天的内置任务"""
        tm.ensure_builtin_tasks()
        today = datetime.now().strftime("%Y-%m-%d")
        tasks = tm.get_tasks_for_date(today, task_type="builtin")
        titles = [t["title"] for t in tasks]
        assert "早间签到" in titles
        assert "每日日报生成" in titles

    def test_idempotent(self, tm):
        """重复调用不重复创建"""
        tm.ensure_builtin_tasks()
        tm.ensure_builtin_tasks()
        today = datetime.now().strftime("%Y-%m-%d")
        tasks = tm.get_tasks_for_date(today, task_type="builtin")
        assert len(tasks) == 3  # 只有3个内置任务


class TestMarkTaskDone:
    """任务完成标记"""

    def test_mark_done(self, tm):
        """标记任务完成"""
        today = datetime.now().strftime("%Y-%m-%d")
        tm.detect_task_list("今日任务：写代码")
        tasks = tm.get_tasks_for_date(today)
        tm.update_task_status(tasks[0]["id"], "done")
        updated = tm.get_tasks_for_date(today)
        assert updated[0]["status"] == "done"

    def test_mark_done_invalid_id(self, tm):
        """标记不存在的任务不报错"""
        tm.update_task_status("nonexistent-id", "done")  # 不应抛异常


class TestGetTasks:
    """任务查询"""

    def test_get_tasks_by_date(self, tm):
        """按日期查询任务"""
        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        tm.detect_task_list("今日任务：写代码")
        # 手动插入昨天的任务
        tm._raw_execute(
            "INSERT INTO tasks (id, title, date, time, status, type, created_at) VALUES (?, ?, ?, '', 'pending', 'user', ?)",
            ("old-1", "昨天的任务", yesterday, datetime.now().isoformat())
        )
        today_tasks = tm.get_tasks_for_date(today)
        assert all(t["date"] == today for t in today_tasks)

    def test_get_today_tasks(self, tm):
        """获取今日任务"""
        tm.detect_task_list("今日任务：A；B")
        tasks = tm.get_today_tasks()
        assert len(tasks) == 2
