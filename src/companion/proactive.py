"""主动提醒引擎

根据规则主动向用户推送提醒。
规则：
1. screen_time_exceeded: 屏幕时间超标
2. entertainment_overuse: 娱乐App使用过久
3. mood_check: 情绪低落关心
4. long_silence: 长时间不聊关心
5. daily_check_in: 每日签到
"""
import logging
from datetime import datetime, timedelta
from typing import Callable, Coroutine, Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ProactiveReminder:
    """主动提醒"""
    rule_name: str = ""
    title: str = ""
    message: str = ""
    priority: str = "normal"  # low, normal, high
    timestamp: datetime = field(default_factory=datetime.now)
    dismissed: bool = False


@dataclass
class ProactiveRule:
    """主动提醒规则"""
    name: str = ""
    title_template: str = ""
    message_template: str = ""
    priority: str = "normal"
    cooldown_hours: int = 6
    enabled: bool = True
    # condition checker is set at runtime
    check_fn: Optional[Callable] = None


class ProactiveEngine:
    """主动干预引擎"""

    def __init__(self, llm=None, memory=None, phone_storage=None):
        self.llm = llm
        self.memory = memory
        self.phone_storage = phone_storage
        self._rules: List[ProactiveRule] = []
        self._last_triggered: Dict[str, datetime] = {}
        self._setup_default_rules()

    def _setup_default_rules(self):
        """设置默认规则"""
        self._rules = [
            ProactiveRule(
                name="mood_check",
                title_template="🎭 情绪关怀",
                message_template="最近情绪似乎有些低落，记得照顾好自己哦～",
                priority="normal",
                cooldown_hours=12,
            ),
            ProactiveRule(
                name="long_silence",
                title_template="👋 好久不见",
                message_template="好久没聊天了，最近怎么样？",
                priority="low",
                cooldown_hours=48,
            ),
            ProactiveRule(
                name="screen_time_exceeded",
                title_template="📱 屏幕时间提醒",
                message_template="今天屏幕时间已经很长了，休息一下眼睛吧～",
                priority="high",
                cooldown_hours=4,
            ),
            ProactiveRule(
                name="daily_check_in",
                title_template="☀️ 早安",
                message_template="新的一天开始了！有什么计划吗？",
                priority="low",
                cooldown_hours=20,
            ),
        ]

    async def check_all_rules(self, context: Optional[Dict] = None) -> List[ProactiveReminder]:
        """检查所有规则，返回需要发送的提醒"""
        reminders = []
        now = datetime.now()

        for rule in self._rules:
            if not rule.enabled:
                continue

            # 检查冷却时间
            last = self._last_triggered.get(rule.name)
            if last and (now - last).total_seconds() < rule.cooldown_hours * 3600:
                continue

            # 执行检查
            should_trigger = await self._check_rule(rule, context or {})
            if should_trigger:
                reminder = ProactiveReminder(
                    rule_name=rule.name,
                    title=rule.title_template,
                    message=rule.message_template,
                    priority=rule.priority,
                )
                reminders.append(reminder)
                self._last_triggered[rule.name] = now

        return reminders

    async def _check_rule(self, rule: ProactiveRule, context: Dict) -> bool:
        """检查单个规则是否触发"""
        if rule.name == "mood_check":
            return await self._check_mood(context)
        elif rule.name == "long_silence":
            return await self._check_silence(context)
        elif rule.name == "screen_time_exceeded":
            return await self._check_screen_time(context)
        elif rule.name == "daily_check_in":
            return self._check_daily_checkin(context)
        return False

    async def _check_mood(self, context: Dict) -> bool:
        """检查情绪是否低落"""
        if not self.memory:
            return False
        try:
            emotions = await self.memory.get_emotions(
                since=datetime.now() - timedelta(hours=24),
                limit=20,
            )
            if not emotions:
                return False
            # 最近情绪中负面情绪占比超过 60%
            negative = ["sad", "anxious", "frustrated", "tired"]
            neg_count = sum(1 for e in emotions if e.emotion in negative)
            return neg_count / len(emotions) > 0.6
        except Exception as e:
            logger.warning(f"情绪检查失败: {e}")
            return False

    async def _check_silence(self, context: Dict) -> bool:
        """检查是否长时间未聊"""
        if not self.memory:
            return False
        try:
            messages = await self.memory.get_messages(limit=5)
            if not messages:
                return True  # 从未聊过
            last_msg = messages[-1]
            hours_since = (datetime.now() - last_msg.timestamp).total_seconds() / 3600
            return hours_since > 48
        except Exception:
            return False

    async def _check_screen_time(self, context: Dict) -> bool:
        """检查屏幕时间是否超标"""
        if not self.phone_storage:
            return False
        try:
            summary = await self.phone_storage.get_summary()
            # 超过 4 小时提醒
            return summary.get("total_screen_time", 0) > 14400
        except Exception:
            return False

    def _check_daily_checkin(self, context: Dict) -> bool:
        """每日签到（总是触发，在守护模式中调用）"""
        return context.get("is_morning", False)

    def add_rule(self, rule: ProactiveRule):
        """添加自定义规则"""
        self._rules.append(rule)

    def get_rules(self) -> List[ProactiveRule]:
        """获取所有规则"""
        return list(self._rules)
