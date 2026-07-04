"""报告生成器 — 日报 / 周报 / 月报

在 daily_report.py 的基础上扩展，生成更全面的报告。
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from src.llm.base import ChatMessage, LLMProvider
from src.memory.base import ConversationMessage, EmotionRecord, ExtractedFact
from src.memory.database import MemoryDatabase

logger = logging.getLogger(__name__)


WEEKLY_REPORT_PROMPT = """你是一个温暖的个人助手。根据以下一周数据，为用户生成一份周报。

## 本周对话统计
总对话数: {total_messages} 条
活跃天数: {active_days} 天

## 每日对话数
{daily_counts}

## 情绪记录
{emotions}

## 本周提取的事实
{facts}

请生成周报，格式如下：
1. 📊 本周概览（总结这周的整体状态）
2. 📅 每日回顾（简要列出每天做了什么）
3. 🎭 情绪趋势（这周情绪如何变化）
4. 📌 值得记住的（重要信息、承诺、目标进展）
5. 💡 小柏的建议（温暖的建议，像朋友一样）

保持简洁，不要超过 800 字。语气温暖自然。
"""

MONTHLY_REPORT_PROMPT = """你是一个温暖的个人助手。根据以下一个月的数据，为用户生成一份月报。

## 本月对话统计
总对话数: {total_messages} 条
活跃天数: {active_days} 天

## 情绪记录
{emotions}

## 本月提取的事实
{facts}

请生成月报，格式如下：
1. 🌟 本月总结（这月的整体成长和变化）
2. 📊 数据概览（对话、情绪、习惯的变化）
3. 🎯 目标进展（之前提到的目标完成了多少）
4. 🎭 情绪画像（这月的情绪分布和趋势）
5. 💡 小柏的总结（温暖的月度寄语）

保持简洁，不要超过 1000 字。语气温暖自然。
"""


class ReportGenerator:
    """报告生成器（日报/周报/月报）"""

    def __init__(self, llm: LLMProvider, memory: MemoryDatabase):
        self.llm = llm
        self.memory = memory

    async def generate_daily_report(self, target_date: Optional[datetime] = None) -> str:
        """生成日报"""
        if target_date is None:
            target_date = datetime.now()

        day_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)

        # 获取当天数据
        all_messages = await self.memory.get_messages(limit=500)
        day_messages = [m for m in all_messages if day_start <= m.timestamp < day_end]
        emotions = await self.memory.get_emotions(since=day_start, limit=100)
        day_emotions = [e for e in emotions if e.timestamp < day_end]
        all_facts = await self.memory.get_facts(limit=200)
        day_facts = [f for f in all_facts if day_start <= f.created_at < day_end]

        if not day_messages and not day_emotions:
            return "今天还没有什么记录，来聊聊天吧！😊"

        # 格式化
        conversation = "\n".join([
            f"[{m.timestamp.strftime('%H:%M')}] {m.role}: {m.content}"
            for m in day_messages
        ]) or "（今天没有对话记录）"

        emotion_text = "\n".join([
            f"[{e.timestamp.strftime('%H:%M')}] {e.emotion} (强度:{e.intensity:.1f}) - {e.context}"
            for e in day_emotions
        ]) or "（没有情绪记录）"

        facts_text = "\n".join([
            f"- [{f.fact_type}] {f.subject}: {f.content}"
            for f in day_facts
        ]) or "（没有提取新信息）"

        from src.companion.daily_report import REPORT_PROMPT
        prompt = REPORT_PROMPT.format(
            conversation=conversation,
            emotions=emotion_text,
            facts=facts_text,
        )

        response = await self.llm.chat(
            messages=[ChatMessage(role="user", content=prompt)],
            temperature=0.5,
            max_tokens=1024,
        )
        return response.content

    async def generate_weekly_report(self, week_start: Optional[datetime] = None) -> str:
        """生成周报"""
        if week_start is None:
            now = datetime.now()
            week_start = now - timedelta(days=now.weekday())

        week_end = week_start + timedelta(days=7)

        # 获取一周数据
        all_messages = await self.memory.get_messages(limit=2000)
        week_messages = [m for m in all_messages if week_start <= m.timestamp < week_end]
        emotions = await self.memory.get_emotions(since=week_start, limit=500)
        week_emotions = [e for e in emotions if e.timestamp < week_end]
        all_facts = await self.memory.get_facts(limit=500)
        week_facts = [f for f in all_facts if week_start <= f.created_at < week_end]

        if not week_messages:
            return "这一周还没有什么记录，来聊聊吧！😊"

        # 按天统计
        daily_counts: Dict[str, int] = {}
        for m in week_messages:
            day = m.timestamp.strftime("%m-%d")
            daily_counts[day] = daily_counts.get(day, 0) + 1

        active_days = len(daily_counts)
        daily_counts_text = "\n".join([
            f"  {day}: {count} 条消息"
            for day, count in sorted(daily_counts.items())
        ])

        emotion_text = "\n".join([
            f"  [{e.timestamp.strftime('%m-%d %H:%M')}] {e.emotion} (强度:{e.intensity:.1f}) - {e.context}"
            for e in week_emotions
        ]) or "（没有情绪记录）"

        facts_text = "\n".join([
            f"  - [{f.fact_type}] {f.subject}: {f.content}"
            for f in week_facts
        ]) or "（没有提取新信息）"

        prompt = WEEKLY_REPORT_PROMPT.format(
            total_messages=len(week_messages),
            active_days=active_days,
            daily_counts=daily_counts_text,
            emotions=emotion_text,
            facts=facts_text,
        )

        response = await self.llm.chat(
            messages=[ChatMessage(role="user", content=prompt)],
            temperature=0.5,
            max_tokens=1536,
        )
        return response.content

    async def generate_monthly_report(self, year: int = None, month: int = None) -> str:
        """生成月报"""
        now = datetime.now()
        if year is None:
            year = now.year
        if month is None:
            month = now.month

        month_start = datetime(year, month, 1)
        if month == 12:
            month_end = datetime(year + 1, 1, 1)
        else:
            month_end = datetime(year, month + 1, 1)

        # 获取一个月数据
        all_messages = await self.memory.get_messages(limit=5000)
        month_messages = [m for m in all_messages if month_start <= m.timestamp < month_end]
        emotions = await self.memory.get_emotions(since=month_start, limit=1000)
        month_emotions = [e for e in emotions if e.timestamp < month_end]
        all_facts = await self.memory.get_facts(limit=1000)
        month_facts = [f for f in all_facts if month_start <= f.created_at < month_end]

        if not month_messages:
            return f"{year}年{month}月还没有什么记录，来聊聊吧！😊"

        # 活跃天数
        active_days = len(set(m.timestamp.strftime("%Y-%m-%d") for m in month_messages))

        # 情绪统计
        emotion_counts: Dict[str, int] = {}
        for e in month_emotions:
            emotion_counts[e.emotion] = emotion_counts.get(e.emotion, 0) + 1
        emotion_text = "\n".join([
            f"  {emo}: {cnt}次"
            for emo, cnt in sorted(emotion_counts.items(), key=lambda x: -x[1])
        ]) or "（没有情绪记录）"

        facts_text = "\n".join([
            f"  - [{f.fact_type}] {f.subject}: {f.content}"
            for f in month_facts
        ]) or "（没有提取新信息）"

        prompt = MONTHLY_REPORT_PROMPT.format(
            total_messages=len(month_messages),
            active_days=active_days,
            emotions=emotion_text,
            facts=facts_text,
        )

        response = await self.llm.chat(
            messages=[ChatMessage(role="user", content=prompt)],
            temperature=0.5,
            max_tokens=2048,
        )
        return response.content
