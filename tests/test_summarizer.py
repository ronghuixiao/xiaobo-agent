"""记忆摘要测试"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock


class TestSummarizer:
    """测试记忆摘要器"""

    def test_summarizer_class_exists(self):
        """摘要器类存在"""
        from src.memory.summarizer import Summarizer
        assert hasattr(Summarizer, 'summarize_day')
        assert hasattr(Summarizer, 'summarize_week')
        assert hasattr(Summarizer, 'get_summary')

    @pytest.mark.asyncio
    async def test_summarize_day_creates_summary(self):
        """按天摘要创建摘要记录"""
        from src.memory.summarizer import Summarizer
        from src.memory.database import MemoryDatabase
        from src.memory.base import ConversationMessage

        db = MemoryDatabase(":memory:")
        await db.initialize()

        # 创建一些对话
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        for i in range(5):
            msg = ConversationMessage(
                session_id="test",
                role="user" if i % 2 == 0 else "assistant",
                content=f"测试消息 {i}",
                timestamp=datetime.now() - timedelta(days=1, hours=i),
            )
            await db.save_message(msg)

        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value=AsyncMock(content="昨天进行了5轮对话，主要讨论了测试相关内容"))

        summarizer = Summarizer(db, mock_llm)
        summary = await summarizer.summarize_day(yesterday)

        assert summary is not None
        assert len(summary) > 0

        await db.close()

    @pytest.mark.asyncio
    async def test_get_summary_returns_stored(self):
        """获取已存储的摘要"""
        from src.memory.summarizer import Summarizer
        from src.memory.database import MemoryDatabase

        db = MemoryDatabase(":memory:")
        await db.initialize()

        # 手动插入摘要
        await db._db.execute("""
            INSERT INTO summaries (id, date, type, content, message_count, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("test-summary", "2026-07-15", "daily", "这是昨天的摘要", 10, datetime.now().isoformat()))
        await db._db.commit()

        summarizer = Summarizer(db, AsyncMock())
        summary = await summarizer.get_summary("2026-07-15", "daily")

        assert summary == "这是昨天的摘要"

        await db.close()

    @pytest.mark.asyncio
    async def test_get_summary_returns_none_if_missing(self):
        """无摘要时返回None"""
        from src.memory.summarizer import Summarizer
        from src.memory.database import MemoryDatabase

        db = MemoryDatabase(":memory:")
        await db.initialize()

        summarizer = Summarizer(db, AsyncMock())
        summary = await summarizer.get_summary("2099-01-01", "daily")

        assert summary is None

        await db.close()

    @pytest.mark.asyncio
    async def test_summarize_day_skips_if_exists(self):
        """已存在摘要时跳过"""
        from src.memory.summarizer import Summarizer
        from src.memory.database import MemoryDatabase

        db = MemoryDatabase(":memory:")
        await db.initialize()

        # 手动插入摘要
        await db._db.execute("""
            INSERT INTO summaries (id, date, type, content, message_count, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("test-summary2", "2026-07-15", "daily", "已存在的摘要", 10, datetime.now().isoformat()))
        await db._db.commit()

        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock()

        summarizer = Summarizer(db, mock_llm)
        summary = await summarizer.summarize_day("2026-07-15")

        assert summary == "已存在的摘要"
        mock_llm.chat.assert_not_called()  # 不应该调用LLM

        await db.close()
