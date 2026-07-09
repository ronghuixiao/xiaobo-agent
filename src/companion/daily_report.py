"""每日报告生成器

在每天指定时间（默认 22:00）生成日报并推送。
包含：今日对话回顾、情绪轨迹、任务完成情况、提取的事实、记忆统计。
改进版：增加更多数据源，深度分析，更有温度的总结。
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import aiosqlite
import os

from src.llm.base import ChatMessage, LLMProvider
from src.memory.base import ConversationMessage, EmotionRecord
from src.memory.database import MemoryDatabase

logger = logging.getLogger(__name__)

# 改进的日报 prompt - 更详细、更有温度、不限制字数
REPORT_PROMPT_V2 = """你是一个温暖、有洞察力的个人助手。根据以下今日数据，为用户生成一份详细、有深度的日报。

## 📊 今日数据概览
- 日期: {date}
- 对话数: {conversation_count} 条
- 情绪记录: {emotion_count} 条
- 新增事实: {fact_count} 条
- 任务完成: {tasks_completed}/{tasks_total} 个

## 💬 今日对话记录
{conversation}

## 🎭 情绪记录
{emotions}

## 📌 今日提取的信息
{facts}

## ✅ 任务完成情况
### 已完成
{tasks_done}

### 未完成
{tasks_pending}

## 📈 昨日对比
- 昨日对话数: {yesterday_conversations} 条

## 重要规则（必须遵守）
- **只基于上面提供的数据写报告**，不要添加任何不存在的内容
- 对话内容要**提炼主题和要点**，不要简单罗列
- 分析用户今天关注的重点、讨论的核心话题
- 任务完成情况要详细说明，而不是只说"完成了X个任务"
- 如果有情绪记录，分析情绪变化趋势
- 如果情绪记录较少，可以说"今天没有记录情绪波动"
- **保持深度和温度**，不要敷衍了事

## 📝 请按以下格式生成日报（至少500字）：

### 🌟 今日总结
用2-3句话概括今天的核心内容，要有洞察力。

### 💬 对话回顾
分析今天聊了什么，提炼出3-5个核心话题或要点。每个要点用1-2句话说明。

### ✅ 任务进展
详细说明每个任务的完成情况：
- 哪些任务完成了？完成得怎么样？
- 哪些任务未完成？可能的原因？
- 整体任务完成率和效率如何？

### 🎭 情绪分析
如果情绪记录较多，分析情绪变化趋势和可能的原因。
如果情绪记录较少，就说"今天没有记录明显的情绪波动"。

### 📌 值得记住的
列出从对话中提取的重要信息或承诺。

### 💡 小柏的建议
基于今天的对话和任务完成情况，给用户1-2条真诚的建议或鼓励。
"""


class DailyReportGenerator:
    """每日报告生成器"""

    def __init__(self, llm: LLMProvider, memory: MemoryDatabase):
        self.llm = llm
        self.memory = memory

    async def _get_tasks_for_date(self, date_str: str) -> List[Dict]:
        """获取指定日期的任务"""
        db_path = os.path.expanduser("~/.xiaobo-agent/memory.db")
        async with aiosqlite.connect(db_path, timeout=10) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM tasks WHERE date = ? ORDER BY time",
                (date_str,),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

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

        # 获取昨天的对话数用于对比
        yesterday_start = day_start - timedelta(days=1)
        all_messages = await self.memory.get_messages(limit=1000)
        yesterday_messages = [
            m for m in all_messages
            if yesterday_start <= m.timestamp < day_start
        ]

        # 获取当天对话
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

        # 获取当天任务
        today_str = target_date.strftime("%Y-%m-%d")
        tasks = await self._get_tasks_for_date(today_str)
        tasks_done = [t for t in tasks if t["status"] == "done"]
        tasks_pending = [t for t in tasks if t["status"] != "done"]

        # 格式化对话内容（提炼要点而不是简单罗列）
        conversation_lines = []
        for m in day_messages:
            # 对长对话做截断，避免 prompt 过长
            content = m.content[:200] + "..." if len(m.content) > 200 else m.content
            conversation_lines.append(f"[{m.timestamp.strftime('%H:%M')}] {m.role}: {content}")
        conversation_text = "\n".join(conversation_lines) or "（今天没有对话记录）"

        # 格式化情绪记录
        emotion_lines = []
        for e in day_emotions:
            emotion_lines.append(
                f"[{e.timestamp.strftime('%H:%M')}] {e.emotion} (强度:{e.intensity:.1f}) - {e.context}"
            )
        emotion_text = "\n".join(emotion_lines) or "（没有情绪记录）"

        # 格式化事实
        facts_lines = []
        for f in day_facts:
            facts_lines.append(f"- [{f.fact_type}] {f.subject}: {f.content}")
        facts_text = "\n".join(facts_lines) or "（没有提取新信息）"

        # 格式化任务
        tasks_done_lines = []
        for t in tasks_done:
            title = t["title"] or "未命名任务"
            tasks_done_lines.append(f"✅ {title}")
        tasks_done_text = "\n".join(tasks_done_lines) or "（没有完成的任务）"

        tasks_pending_lines = []
        for t in tasks_pending:
            title = t["title"] or "未命名任务"
            tasks_pending_lines.append(f"⬜ {title}")
        tasks_pending_text = "\n".join(tasks_pending_lines) or "（所有任务都已完成！）"

        # 如果完全没有数据，直接返回提示，不调用 LLM
        if not day_messages and not day_emotions and not day_facts and not tasks:
            return (
                "📋 今日日报\n\n"
                "今天还没有对话记录呢。\n"
                "和我聊聊天，我就能帮你记录和总结了！"
            )

        # 计算任务完成率
        total_tasks = len(tasks)
        completed_tasks = len(tasks_done)

        # 调用 LLM 生成报告
        prompt = REPORT_PROMPT_V2.format(
            date=target_date.strftime("%Y-%m-%d %A"),
            conversation_count=len(day_messages),
            emotion_count=len(day_emotions),
            fact_count=len(day_facts),
            tasks_completed=completed_tasks,
            tasks_total=total_tasks,
            conversation=conversation_text,
            emotions=emotion_text,
            facts=facts_text,
            tasks_done=tasks_done_text,
            tasks_pending=tasks_pending_text,
            yesterday_conversations=len(yesterday_messages),
        )

        response = await self.llm.chat(
            messages=[ChatMessage(role="user", content=prompt)],
            temperature=0.7,  # 提高温度让内容更丰富
            max_tokens=2048,  # 增加 token 上限
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
