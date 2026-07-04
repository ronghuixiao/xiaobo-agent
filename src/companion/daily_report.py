"""每日报告生成器

在每天指定时间（默认 22:00）生成日报并推送。
包含：今日对话回顾、情绪轨迹、提取的事实、记忆统计。
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from src.llm.base import ChatMessage, LLMProvider
from src.memory.base import ConversationMessage, EmotionRecord
from src.memory.database import MemoryDatabase

logger = logging.getLogger(__name__)

REPORT_PROMPT = """你是一个温暖的个人助手。根据以下今日数据，为用户生成一份简洁的日报。

## 今日对话记录
{conversation}

## 情绪记录
{emotions}

## 今日提取的信息
{facts}

请生成日报，格式如下：
1. 📋 今日概览（一两句话总结今天）
2. 💬 对话回顾（提到了什么，做了什么决定）
3. 🎭 情绪轨迹（今天情绪如何变化）
4. 📌 值得记住的（重要信息、承诺、偏好）
5. 💡 你的话（温暖的一两句话，像朋友一样）

保持简洁，不要超过 500 字。语气温暖自然。
"""


class DailyReportGenerator:
    """每日报告生成器"""

    def __init__(self, llm: LLMProvider, memory: MemoryDatabase):
        self.llm = llm
        self.memory = memory

    async def generate_daily_report(
        self,
        target_date: Optional[datetime] = None,
    ) -> str:
        """生成指定日期的日报"""
        if target_date is None:
            target_date = datetime.now()

        # 获取当天的起止时间
        day_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)

        # 获取当天对话
        all_messages = await self.memory.get_messages(limit=500)
        day_messages = [
            m for m in all_messages
            if day_start <= m.timestamp < day_end
        ]

        # 获取当天情绪
        emotions = await self.memory.get_emotions(since=day_start, limit=100)
        day_emotions = [e for e in emotions if e.timestamp < day_end]

        # 获取当天提取的事实
        all_facts = await self.memory.get_facts(limit=200)
        day_facts = [
            f for f in all_facts
            if day_start <= f.created_at < day_end
        ]

        # 格式化数据
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

        # 调用 LLM 生成报告
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

    async def generate_weekly_summary(self) -> str:
        """生成周报摘要"""
        now = datetime.now()
        week_start = now - timedelta(days=7)

        all_messages = await self.memory.get_messages(limit=1000)
        week_messages = [m for m in all_messages if m.timestamp >= week_start]

        emotions = await self.memory.get_emotions(since=week_start, limit=200)

        # 按天分组
        daily_counts: Dict[str, int] = {}
        for m in week_messages:
            day = m.timestamp.strftime("%m-%d")
            daily_counts[day] = daily_counts.get(day, 0) + 1

        lines = [f"过去7天概览："]
        lines.append(f"  总对话数: {len(week_messages)} 条")
        lines.append(f"  活跃天数: {len(daily_counts)} 天")
        lines.append(f"  情绪记录: {len(emotions)} 条")

        for day, count in sorted(daily_counts.items()):
            lines.append(f"  {day}: {count} 条消息")

        return "\n".join(lines)
