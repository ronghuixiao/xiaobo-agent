"""CommandDispatcher 单元测试"""

import pytest
from unittest.mock import AsyncMock, MagicMock


class TestCommandDispatcher:
    """命令分发器测试"""

    @pytest.fixture
    def dispatcher(self):
        """创建 CommandDispatcher 实例（所有依赖用 mock）"""
        from src.companion.command_dispatcher import CommandDispatcher

        # Mock 所有依赖
        daily_report = AsyncMock()
        daily_report.generate_daily_report.return_value = "今日日报内容"

        report_gen = AsyncMock()
        report_gen.generate_weekly_report.return_value = "周报内容"
        report_gen.generate_monthly_report.return_value = "月报内容"

        tracker = AsyncMock()
        tracker.get_emotion_summary.return_value = "情绪摘要内容"

        analyzer = AsyncMock()
        analyzer.analyze_weekly_pattern.return_value = {
            "total_messages": 42,
            "busiest_day": "周一",
            "quietest_day": "周日",
        }

        memory = AsyncMock()
        memory.get_stats.return_value = {"conversations": 100}

        handler = AsyncMock()
        handler.handle_message.return_value = "对话回复"

        task_mgr = MagicMock()

        llm = MagicMock()  # Mock LLM for task completion detection

        return CommandDispatcher(
            daily_report=daily_report,
            report_gen=report_gen,
            tracker=tracker,
            analyzer=analyzer,
            memory=memory,
            handler=handler,
            task_mgr=task_mgr,
            llm=llm,
        )

    @pytest.mark.asyncio
    async def test_daily_report_command(self, dispatcher):
        """测试 '日报' 命令"""
        result = await dispatcher.dispatch("日报")
        assert result == "📋 今日日报\n\n今日日报内容"

    @pytest.mark.asyncio
    async def test_weekly_report_command(self, dispatcher):
        """测试 '周报' 命令"""
        result = await dispatcher.dispatch("周报")
        assert result == "📋 周报\n\n周报内容"

    @pytest.mark.asyncio
    async def test_monthly_report_command(self, dispatcher):
        """测试 '月报' 命令"""
        result = await dispatcher.dispatch("月报")
        assert result == "📋 月报\n\n月报内容"

    @pytest.mark.asyncio
    async def test_emotion_command(self, dispatcher):
        """测试 '情绪' 命令"""
        result = await dispatcher.dispatch("情绪")
        assert result == "🎭 情绪摘要\n\n情绪摘要内容"

    @pytest.mark.asyncio
    async def test_pattern_command(self, dispatcher):
        """测试 '模式' 命令"""
        result = await dispatcher.dispatch("模式")
        assert "42" in result
        assert "周一" in result

    @pytest.mark.asyncio
    async def test_stats_command(self, dispatcher):
        """测试 '统计' 命令"""
        result = await dispatcher.dispatch("统计")
        assert "100" in result

    @pytest.mark.asyncio
    async def test_unknown_command_falls_through(self, dispatcher):
        """测试未知消息走对话流程"""
        result = await dispatcher.dispatch("今天天气真好")
        assert result == "对话回复"
        dispatcher.handler.handle_message.assert_called_once_with("今天天气真好")

    @pytest.mark.asyncio
    async def test_task_detection_before_reply(self, dispatcher):
        """测试对话前触发任务检测"""
        await dispatcher.dispatch("今日任务：写代码")
        dispatcher.task_mgr.detect_task_list.assert_called_once_with("今日任务：写代码")

    @pytest.mark.asyncio
    async def test_task_completion_after_reply(self, dispatcher):
        """测试对话后触发任务完成检测"""
        await dispatcher.dispatch("做完了写代码的任务")
        # detect_task_completion 被调用两次：一次传用户消息，一次传回复
        assert dispatcher.task_mgr.detect_task_completion.call_count == 2

    @pytest.mark.asyncio
    async def test_is_known_command(self, dispatcher):
        """测试命令识别"""
        assert dispatcher.is_known_command("日报") is True
        assert dispatcher.is_known_command("周报") is True
        assert dispatcher.is_known_command("情绪") is True
        assert dispatcher.is_known_command("今天天气真好") is False
