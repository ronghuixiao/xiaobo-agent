"""任务管理器

使用 MemoryDatabase 进行所有数据操作，不再直接操作 sqlite3。
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

from src.memory.database import MemoryDatabase

logger = logging.getLogger(__name__)


class TaskManager:
    """任务管理器

    封装所有任务相关的业务逻辑。
    通过 MemoryDatabase 进行数据操作。
    """

    def __init__(self, db: MemoryDatabase):
        self.db = db

    # ==================== 任务检测 ====================

    async def detect_task_list(self, message: str) -> None:
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

        # 获取今天的现有用户任务
        existing = await self.db.get_tasks_for_date(today, task_type="user")
        existing_map = {t["title"]: (t["id"], t["status"]) for t in existing}

        new_count = 0
        reset_count = 0
        for task_title in tasks:
            if task_title in existing_map:
                task_id, current_status = existing_map[task_title]
                if current_status == 'done':
                    await self.db.update_task_status(task_id, "pending")
                    reset_count += 1
                    logger.info(f"🔄 重置任务: {task_title} (done → pending)")
            else:
                task_id = f"user-{today}-{hash(task_title) % 1000000:06d}"
                await self.db.save_task(
                    title=task_title,
                    date_str=today,
                    task_type="user",
                    task_id=task_id,
                )
                new_count += 1
                logger.info(f"📝 新增任务: {task_title}")

        if new_count > 0 or reset_count > 0:
            parts = []
            if new_count > 0:
                parts.append(f"{new_count}个新任务")
            if reset_count > 0:
                parts.append(f"{reset_count}个重置")
            logger.info(f"✅ 今日任务已更新: {', '.join(parts)}")

    # ==================== 任务完成检测 ====================

    def detect_task_completion(self, message: str, llm=None) -> None:
        """检测对话中是否提到任务完成，并更新任务状态

        在后台线程中运行，不阻塞主流程。
        """
        if llm is None:
            return

        logger.info(f"🔍 检测任务完成: {message[:50]}...")

        db = self.db  # 捕获引用

        def _run_async():
            async def _async_detect():
                try:
                    today = datetime.now().strftime("%Y-%m-%d")
                    pending_tasks = await db.get_tasks_for_date(today)
                    pending_tasks = [t for t in pending_tasks if t["status"] == "pending"]

                    if not pending_tasks:
                        logger.info("🔍 无待办任务，跳过检测")
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
                                        await db.update_task_status(task_id, "done")
                                        logger.info(f"✅ 任务已完成(LLM检测): {task_id}")
                    except (json.JSONDecodeError, KeyError, TypeError) as e:
                        logger.warning(f"解析LLM任务完成检测结果失败: {e}")

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

    async def ensure_builtin_tasks(self) -> None:
        """创建当天的内置系统任务"""
        today = datetime.now().strftime("%Y-%m-%d")
        existing = await self.db.get_tasks_for_date(today, task_type="builtin")
        if not existing:
            builtin_tasks = [
                ("早间签到", "08:00"),
                ("主动关怀检查", "09:00"),
                ("每日日报生成", "22:00"),
            ]
            for title, time_str in builtin_tasks:
                task_id = f"today-{today}-{time_str.replace(':', '')}"
                await self.db.save_task(
                    title=title,
                    date_str=today,
                    time_str=time_str,
                    task_type="builtin",
                    task_id=task_id,
                )
            logger.info(f"✅ Created {len(builtin_tasks)} builtin tasks for today")

    # ==================== 任务查询（代理到 db） ====================

    async def get_tasks_for_date(self, date_str: str, task_type: Optional[str] = None):
        return await self.db.get_tasks_for_date(date_str, task_type)

    async def get_today_tasks(self):
        return await self.db.get_today_tasks()

    async def get_pending_tasks_with_time(self, date_str: str):
        """获取指定日期的待办任务（不要求有时间字段）"""
        tasks = await self.db.get_tasks_for_date(date_str)
        return [t for t in tasks if t["status"] == "pending"]

    async def move_pending_tasks(self, from_date: str, to_date: str) -> int:
        """将指定日期的待办任务移动到另一个日期"""
        return await self.db.move_pending_tasks(from_date, to_date)

    async def update_task_status(self, task_id: str, status: str):
        await self.db.update_task_status(task_id, status)

    async def mark_done_by_prefix(self, prefix: str):
        await self.db.mark_done_by_prefix(prefix)
