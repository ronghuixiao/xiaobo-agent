"""记忆摘要器

将旧对话压缩成摘要，节省上下文空间。
"""
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional

from src.llm.base import ChatMessage, LLMProvider
from src.memory.database import MemoryDatabase

logger = logging.getLogger(__name__)

SUMMARIZE_PROMPT = """你是一个对话摘要助手。请将以下对话压缩成1-2句简洁的摘要。

对话内容：
{messages}

要求：
1. 保留关键信息（谁说了什么、做了什么决定）
2. 保留时间线索
3. 不要添加对话中没有的信息
4. 用自然语言描述，不要列表格式

摘要："""


class Summarizer:
    """记忆摘要器"""

    def __init__(self, db: MemoryDatabase, llm: LLMProvider):
        self.db = db
        self.llm = llm

    async def get_summary(self, date_str: str, summary_type: str = "daily") -> Optional[str]:
        """获取已存储的摘要"""
        cursor = await self.db._db.execute(
            "SELECT content FROM summaries WHERE date = ? AND type = ?",
            (date_str, summary_type)
        )
        row = await cursor.fetchone()
        return row["content"] if row else None

    async def summarize_day(self, date_str: str) -> Optional[str]:
        """按天摘要"""
        # 检查是否已存在
        existing = await self.get_summary(date_str, "daily")
        if existing:
            return existing

        # 获取当天的对话
        cursor = await self.db._db.execute(
            "SELECT role, content, timestamp FROM conversations WHERE date(timestamp) = ? ORDER BY timestamp",
            (date_str,)
        )
        rows = await cursor.fetchall()

        if not rows:
            return None

        # 格式化对话
        messages_text = "\n".join([
            f"[{row['timestamp']}] {'用户' if row['role'] == 'user' else '小柏'}: {row['content'][:100]}"
            for row in rows[:20]  # 最多取20条
        ])

        # 调用LLM生成摘要
        try:
            response = await self.llm.chat([
                ChatMessage(role="user", content=SUMMARIZE_PROMPT.format(messages=messages_text))
            ])
            summary = response.content

            # 存储摘要
            summary_id = f"summary-{date_str}-daily"
            await self.db._db.execute("""
                INSERT OR REPLACE INTO summaries (id, date, type, content, message_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (summary_id, date_str, "daily", summary, len(rows), datetime.now().isoformat()))
            await self.db._db.commit()

            logger.info(f"📝 生成每日摘要: {date_str} ({len(rows)}条对话)")
            return summary

        except Exception as e:
            logger.warning(f"生成摘要失败: {e}")
            return None

    async def summarize_week(self, start_date: str) -> Optional[str]:
        """按周摘要"""
        # 检查是否已存在
        existing = await self.get_summary(start_date, "weekly")
        if existing:
            return existing

        # 获取一周的对话
        start = datetime.fromisoformat(start_date)
        end = start + timedelta(days=7)

        cursor = await self.db._db.execute(
            "SELECT role, content, timestamp FROM conversations WHERE timestamp >= ? AND timestamp < ? ORDER BY timestamp",
            (start.isoformat(), end.isoformat())
        )
        rows = await cursor.fetchall()

        if not rows:
            return None

        # 格式化对话（取摘要版）
        messages_text = "\n".join([
            f"[{row['timestamp']}] {'用户' if row['role'] == 'user' else '小柏'}: {row['content'][:80]}"
            for row in rows[:50]  # 最多取50条
        ])

        # 调用LLM生成周摘要
        try:
            response = await self.llm.chat([
                ChatMessage(role="user", content=f"请将以下一周的对话压缩成3-5句摘要：\n\n{messages_text}")
            ])
            summary = response.content

            # 存储摘要
            summary_id = f"summary-{start_date}-weekly"
            await self.db._db.execute("""
                INSERT OR REPLACE INTO summaries (id, date, type, content, message_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (summary_id, start_date, "weekly", summary, len(rows), datetime.now().isoformat()))
            await self.db._db.commit()

            logger.info(f"📝 生成每周摘要: {start_date} ({len(rows)}条对话)")
            return summary

        except Exception as e:
            logger.warning(f"生成周摘要失败: {e}")
            return None
