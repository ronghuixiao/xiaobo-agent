"""模式分析器测试"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

from src.companion.pattern_analyzer import PatternAnalyzer


class TestPatternAnalyzer:
    """PatternAnalyzer 测试"""

    @pytest.fixture
    def mock_memory(self):
        """模拟记忆数据库"""
        memory = AsyncMock()
        memory.get_messages = AsyncMock(return_value=[])
        memory.get_emotions = AsyncMock(return_value=[])
        memory.get_facts = AsyncMock(return_value=[])
        return memory

    @pytest.mark.asyncio
    async def test_weekly_pattern_empty(self, mock_memory):
        """测试无数据时的周模式"""
        analyzer = PatternAnalyzer(mock_memory)
        result = await analyzer.analyze_weekly_pattern()
        assert "total_messages" in result
        assert result["total_messages"] == 0

    @pytest.mark.asyncio
    async def test_weekly_pattern_with_data(self, mock_memory):
        """测试有数据时的周模式"""
        from src.memory.base import ConversationMessage
        now = datetime.now()
        messages = [
            ConversationMessage(session_id="s1", role="user", content=f"消息{i}",
                              timestamp=now - timedelta(hours=i))
            for i in range(10)
        ]
        mock_memory.get_messages = AsyncMock(return_value=messages)

        analyzer = PatternAnalyzer(mock_memory)
        result = await analyzer.analyze_weekly_pattern()
        assert result["total_messages"] == 10
        assert "busiest_day" in result
        assert "weekday_distribution" in result

    @pytest.mark.asyncio
    async def test_detect_habit_changes_empty(self, mock_memory):
        """测试无数据时的习惯变化检测"""
        analyzer = PatternAnalyzer(mock_memory)
        changes = await analyzer.detect_habit_changes()
        assert isinstance(changes, list)
        assert len(changes) > 0  # 至少有"模式稳定"的提示

    @pytest.mark.asyncio
    async def test_activity_heatmap(self, mock_memory):
        """测试活动热力图"""
        analyzer = PatternAnalyzer(mock_memory)
        result = await analyzer.get_activity_heatmap(weeks=4)
        assert "heatmap" in result
        assert len(result["heatmap"]) == 7  # 7 天
        assert len(result["heatmap"][0]) == 24  # 24 小时

    @pytest.mark.asyncio
    async def test_predict_mood_empty(self, mock_memory):
        """测试无数据时的情绪预测"""
        analyzer = PatternAnalyzer(mock_memory)
        result = await analyzer.predict_mood()
        assert "prediction" in result
        assert result["confidence"] == 0

    def test_analyzer_init(self, mock_memory):
        """测试初始化"""
        analyzer = PatternAnalyzer(mock_memory)
        assert analyzer.memory == mock_memory
