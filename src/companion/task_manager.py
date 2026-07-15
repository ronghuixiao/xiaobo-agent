"""任务管理器

从 main.py 提取的任务相关逻辑：
- 从文本中检测任务列表
- 任务 CRUD 操作
- 内置任务管理
- 任务完成检测（LLM）
"""

import json
import logging
import os
import re
import sqlite3
import threading
import asyncio
from datetime import datetime, date
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class TaskManager:
    """任务管理器

    封装所有任务相关的数据库操作和业务逻辑。
    Phase 1 仍使用裸 sqlite3，Phase 2 将统一到 MemoryDatabase。
    """

    def __init__(self, db_path: str = "~/.xiaobo-agent/memory.db"):
        self.db_path = os.path.expanduser(db_path)

    def _connect(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _raw_execute(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """直接执行 SQL 查询（测试辅助用）"""
        conn = self._connect()
        try:
            cursor = conn.execute(sql, params)
            conn.commit()
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    # ==================== 任务检测 ====================

    def detect_task_list(self, message: str) -> None:
        """检测用户输入的任务列表并保存到数据库

        识别格式：
        - 今日任务：A；B；C
        - 任务清单：A、B、C
        - 今天要做：A, B, C
        """
        patterns = [
            r'今日任务[：:]\s*(.+)',
            r'任务清单[：:]\s*(.+)',
            r'今天要做[：:]\s*(.+)',
            r'今天的任务[：:]\s*(.+)',
            r'今日待办[：:]\s*(.+)',
        ]

        tasks = []
        for pattern in patterns:
            match = re.search(pattern, message)
            if match:
                task_str = match.group(1)
                tasks = re.split(r'[；;、，,]', task_str)
                tasks = [t.strip() for t in tasks if t.strip()]
                break

        if not tasks:
            return

        today = datetime.now().strftime("%Y-%m-%d")
        conn = self._connect()
        try:
            existing = conn.execute(
                "SELECT id, title, status FROM tasks WHERE date = ? AND type = 'user'",
                (today,)
            ).fetchall()
            existing_map = {row["title"]: (row["id"], row["status"]) for row in existing}

            new_count = 0
            reset_count = 0
            for task_title in tasks:
                if task_title in existing_map:
                    task_id, current_status = existing_map[task_title]
                    if current_status == 'done':
                        conn.execute(
                            "UPDATE tasks SET status = 'pending' WHERE id = ?",
                            (task_id,)
                        )
                        reset_count += 1
                        logger.info(f"🔄 重置任务: {task_title} (done → pending)")
                else:
                    task_id = f"user-{today}-{hash(task_title) % 1000000:06d}"
                    conn.execute(
                        "INSERT INTO tasks (id, title, date, time, status, type, created_at) VALUES (?, ?, ?, '', 'pending', 'user', ?)",
                        (task_id, task_title, today, datetime.now().isoformat())
                    )
                    new_count += 1
                    logger.info(f"📝 新增任务: {task_title}")

            if new_count > 0 or reset_count > 0:
                conn.commit()
                parts = []
                if new_count > 0:
                    parts.append(f"{new_count}个新任务")
                if reset_count > 0:
                    parts.append(f"{reset_count}个重置")
                logger.info(f"✅ 今日任务已更新: {', '.join(parts)}")
        finally:
            conn.close()

    # ==================== 任务完成检测 ====================

    def detect_task_completion(self, message: str, llm=None) -> None:
        """检测对话中是否提到任务完成，并更新任务状态

        Args:
            message: 用户消息
            llm: LLMProvider 实例（可选，传入时启用 LLM 检测）
        """
        if llm is None:
            return

        logger.info(f"🔍 检测任务完成: {message[:50]}...")

        def _run_async():
            async def _async_detect():
                try:
                    conn = self._connect()
                    today = datetime.now().strftime("%Y-%m-%d")

                    pending_tasks = conn.execute(
                        "SELECT id, title FROM tasks WHERE date = ? AND status = 'pending'",
                        (today,)
                    ).fetchall()

                    if not pending_tasks:
                        logger.info("🔍 无待办任务，跳过检测")
                        conn.close()
                        return

                    logger.info(f"🔍 待办任务: {[t['title'] for t in pending_tasks]}")

                    task_list = "\n".join([f"- {t['id']}: {t['title']}" for t in pending_tasks])

                    from src.llm.base import ChatMessage
                    prompt = f"""判断用户消息中是否表达了某个任务已完成。
今天的待办任务：
{task_list}
用户消息："{message}"
规则：
- 判断是否表达"完成了/做完了/搞定了/OK了/结束了/通过了/交了/过了"等任何完成含义
- 只匹配列表中的任务
- 返回JSON数组，格式为[{{"task_id": "xxx", "completed": true}}]，没有匹配返回[]
只返回JSON。"""

                    response = await llm.chat([ChatMessage(role="user", content=prompt)])
                    logger.info(f"🔍 LLM响应: {response.content[:200]}")

                    try:
                        response_text = response.content
                        start_idx = response_text.find('[')
                        end_idx = response_text.rfind(']') + 1
                        if start_idx != -1 and end_idx != -1:
                            json_str = response_text[start_idx:end_idx]
                            completed_tasks = json.loads(json_str)
                            logger.info(f"🔍 解析到完成任务: {completed_tasks}")

                            for task in completed_tasks:
                                if task.get("completed") and task.get("task_id"):
                                    task_id = task["task_id"]
                                    if any(t["id"] == task_id for t in pending_tasks):
                                        conn.execute("UPDATE tasks SET status = 'done' WHERE id = ?", (task_id,))
                                        logger.info(f"✅ 任务已完成(LLM检测): {task_id}")
                    except (json.JSONDecodeError, KeyError, TypeError) as e:
                        logger.warning(f"解析LLM任务完成检测结果失败: {e}")

                    conn.commit()
                    conn.close()
                except Exception as e:
                    logger.warning(f"检测任务完成失败: {e}", exc_info=True)

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(_async_detect())
            finally:
                loop.close()

        thread = threading.Thread(target=_run_async, daemon=True)
        thread.start()

    # ==================== 内置任务 ====================

    def ensure_builtin_tasks(self) -> None:
        """创建当天的内置系统任务"""
        conn = self._connect()
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            existing = conn.execute(
                "SELECT id FROM tasks WHERE date = ? AND type = 'builtin'",
                (today,)
            ).fetchall()
            if not existing:
                builtin_tasks = [
                    (f"today-{today}-0800", "早间签到", "08:00", today, "pending", "builtin"),
                    (f"today-{today}-0900", "主动关怀检查", "09:00", today, "pending", "builtin"),
                    (f"today-{today}-2200", "每日日报生成", "22:00", today, "pending", "builtin"),
                ]
                for t in builtin_tasks:
                    conn.execute(
                        "INSERT OR IGNORE INTO tasks (id, title, time, date, status, type, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (*t, datetime.now().isoformat())
                    )
                conn.commit()
                logger.info(f"✅ Created {len(builtin_tasks)} builtin tasks for today")
        finally:
            conn.close()

    # ==================== 任务查询 ====================

    def get_tasks_for_date(
        self,
        date_str: str,
        task_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """获取指定日期的任务"""
        conn = self._connect()
        try:
            if task_type:
                rows = conn.execute(
                    "SELECT * FROM tasks WHERE date = ? AND type = ? ORDER BY time",
                    (date_str, task_type)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM tasks WHERE date = ? ORDER BY time",
                    (date_str,)
                ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_today_tasks(self) -> List[Dict[str, Any]]:
        """获取今日任务"""
        today = datetime.now().strftime("%Y-%m-%d")
        return self.get_tasks_for_date(today)

    def get_all_tasks(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取所有任务（按日期倒序）"""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM tasks ORDER BY date DESC, time LIMIT ?",
                (limit,)
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_pending_tasks_with_time(self, date_str: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取有时间的待办任务（用于提醒检查）"""
        if date_str is None:
            date_str = datetime.now().strftime("%Y-%m-%d")
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE date <= ? AND status = 'pending' AND time != '' AND time IS NOT NULL ORDER BY date, time",
                (date_str,)
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    # ==================== 任务修改 ====================

    def update_task_status(self, task_id: str, status: str) -> None:
        """更新任务状态"""
        conn = self._connect()
        try:
            conn.execute("UPDATE tasks SET status = ? WHERE id = ?", (status, task_id))
            conn.commit()
        finally:
            conn.close()

    def create_task(
        self,
        title: str,
        date_str: str = "",
        time_str: str = "",
        task_type: str = "user",
    ) -> str:
        """创建任务，返回任务 ID"""
        import uuid
        if not date_str:
            date_str = datetime.now().strftime("%Y-%m-%d")
        task_id = "task-" + str(uuid.uuid4())[:8]
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO tasks (id, title, date, time, status, type, created_at) VALUES (?, ?, ?, ?, 'pending', ?, ?)",
                (task_id, title, date_str, time_str, task_type, datetime.now().isoformat())
            )
            conn.commit()
        finally:
            conn.close()
        return task_id

    def mark_done_by_prefix(self, prefix: str) -> None:
        """按前缀标记任务完成"""
        conn = self._connect()
        try:
            today = date.today().isoformat()
            rows = conn.execute(
                "SELECT id FROM tasks WHERE id LIKE ? AND date = ? AND status = 'pending'",
                (prefix + "%", today)
            ).fetchall()
            for row in rows:
                conn.execute("UPDATE tasks SET status = 'done' WHERE id = ?", (row["id"],))
                logger.info(f"✅ task done: {row['id']}")
            conn.commit()
        finally:
            conn.close()
