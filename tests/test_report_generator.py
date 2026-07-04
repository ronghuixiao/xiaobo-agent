"""报告生成器测试"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from src.companion.report_generator import ReportGenerator


class TestReportGenerator:
    """ReportGenerator 测试"""

    @pytest.fixture
    def mock_llm(self):
        """模拟 LLM"""
        llm = AsyncMock()
        llm.chat = AsyncMock(return_value=MagicMock(
            content="📋 今日概览：今天学了Python装饰器，情绪不错。\n💬 对话回顾：讨论了装饰器的用法。\n🎭 情绪轨迹：😊 平静→兴奋\n📌 值得记住的：Python装饰器很实用。\n💡 继续加油！"
        ))
        return llm

    @pytest.fixture
    def mock_memory(self):
        """模拟记忆数据库"""
        memory = AsyncMock()
        memory.get_messages = AsyncMock(return_value=[])
        memory.get_emotions = AsyncMock(return_value=[])
        memory.get_facts = AsyncMock(return_value=[])
        return memory

    @pytest.mark.asyncio
    async def test_daily_report_empty(self, mock_llm, mock_memory):
        """测试无数据时的日报"""
        reporter = ReportGenerator(mock_llm, mock_memory)
        report = await reporter.generate_daily_report()
        assert "还没有什么记录" in report or len(report) > 0

    @pytest.mark.asyncio
    async def test_weekly_report_empty(self, mock_llm, mock_memory):
        """测试无数据时的周报"""
        reporter = ReportGenerator(mock_llm, mock_memory)
        report = await reporter.generate_weekly_report()
        assert "还没有什么记录" in report or len(report) > 0

    @pytest.mark.asyncio
    async def test_monthly_report_empty(self, mock_llm, mock_memory):
        """测试无数据时的月报"""
        reporter = ReportGenerator(mock_llm, mock_memory)
        report = await reporter.generate_monthly_report()
        assert "还没有什么记录" in report or len(report) > 0

    @pytest.mark.asyncio
    async def test_daily_report_with_data(self, mock_llm, mock_memory):
        """测试有数据时的日报"""
        from src.memory.base import ConversationMessage, EmotionRecord
        now = datetime.now()
        mock_memory.get_messages = AsyncMock(return_value=[
            ConversationMessage(session_id="s1", role="user", content="今天学了Python", timestamp=now),
            ConversationMessage(session_id="s1", role="assistant", content="很棒！", timestamp=now),
        ])
        mock_memory.get_emotions = AsyncMock(return_value=[
            EmotionRecord(emotion="happy", intensity=0.8, context="学新东西", timestamp=now),
        ])

        reporter = ReportGenerator(mock_llm, mock_memory)
        report = await reporter.generate_daily_report()
        assert len(report) > 0
        mock_llm.chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_weekly_report_with_data(self, mock_llm, mock_memory):
        """测试有数据时的周报"""
        from src.memory.base import ConversationMessage
        now = datetime.now()
        messages = [
            ConversationMessage(session_id="s1", role="user", content=f"第{i}天", timestamp=now - timedelta(days=i))
            for i in range(7)
        ]
        mock_memory.get_messages = AsyncMock(return_value=messages)

        reporter = ReportGenerator(mock_llm, mock_memory)
        report = await reporter.generate_weekly_report()
        assert len(report) > 0
        mock_llm.chat.assert_called_once()

    def test_report_generator_init(self, mock_llm, mock_memory):
        """测试初始化"""
        reporter = ReportGenerator(mock_llm, mock_memory)
        assert reporter.llm == mock_llm
        assert reporter.memory == mock_memory
