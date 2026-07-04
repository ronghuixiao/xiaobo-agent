"""主动提醒引擎测试"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from src.companion.proactive import ProactiveEngine, ProactiveReminder, ProactiveRule


class TestProactiveEngine:
    """ProactiveEngine 测试"""

    def test_engine_init(self):
        """测试引擎初始化"""
        engine = ProactiveEngine()
        assert len(engine.get_rules()) == 4

    def test_rules_have_names(self):
        """测试规则有名称"""
        engine = ProactiveEngine()
        names = [r.name for r in engine.get_rules()]
        assert "mood_check" in names
        assert "long_silence" in names
        assert "screen_time_exceeded" in names
        assert "daily_check_in" in names

    def test_add_custom_rule(self):
        """测试添加自定义规则"""
        engine = ProactiveEngine()
        engine.add_rule(ProactiveRule(
            name="custom_rule",
            title_template="🔔 自定义提醒",
            message_template="这是一条自定义提醒",
        ))
        assert len(engine.get_rules()) == 5

    @pytest.mark.asyncio
    async def test_daily_checkin_triggers_in_morning(self):
        """测试早晨签到触发"""
        engine = ProactiveEngine()
        context = {"is_morning": True}
        reminders = await engine.check_all_rules(context)
        morning = [r for r in reminders if r.rule_name == "daily_check_in"]
        assert len(morning) == 1

    @pytest.mark.asyncio
    async def test_daily_checkin_not_trigger_at_night(self):
        """测试晚上不触发签到"""
        engine = ProactiveEngine()
        context = {"is_morning": False}
        reminders = await engine.check_all_rules(context)
        morning = [r for r in reminders if r.rule_name == "daily_check_in"]
        assert len(morning) == 0

    @pytest.mark.asyncio
    async def test_cooldown_prevents_repeat(self):
        """测试冷却时间防止重复触发"""
        engine = ProactiveEngine()
        context = {"is_morning": True}
        # 第一次触发
        reminders1 = await engine.check_all_rules(context)
        assert len(reminders1) >= 1
        # 立即再触发，应该被冷却阻止
        reminders2 = await engine.check_all_rules(context)
        morning2 = [r for r in reminders2 if r.rule_name == "daily_check_in"]
        assert len(morning2) == 0

    @pytest.mark.asyncio
    async def test_disabled_rule_not_triggered(self):
        """测试禁用的规则不触发"""
        engine = ProactiveEngine()
        engine._rules[0].enabled = False  # 禁用第一个规则
        rules_before = len(engine._rules)
        reminders = await engine.check_all_rules({"is_morning": True})
        # 至少 daily_check_in 应该触发，但我们禁用了 mood_check
        disabled_rule = engine._rules[0]
        assert not any(r.rule_name == disabled_rule.name for r in reminders)

    def test_reminder_dataclass(self):
        """测试提醒数据类"""
        reminder = ProactiveReminder(
            rule_name="test",
            title="测试标题",
            message="测试消息",
            priority="high",
        )
        assert reminder.rule_name == "test"
        assert not reminder.dismissed

    def test_rule_dataclass(self):
        """测试规则数据类"""
        rule = ProactiveRule(
            name="test_rule",
            title_template="测试",
            message_template="消息",
            cooldown_hours=12,
        )
        assert rule.name == "test_rule"
        assert rule.enabled is True
