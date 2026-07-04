"""情绪追踪模块

从对话中追踪情绪变化，生成情绪时间线。
支持：
- 单条消息情绪分析
- 情绪趋势分析（上升/下降/波动）
- 情绪摘要（一段时间内的情绪概况）
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from src.llm.base import ChatMessage, LLMProvider
from src.memory.base import EmotionRecord, EmotionType
from src.memory.database import MemoryDatabase

logger = logging.getLogger(__name__)

EMOTION_LABELS = {
    "happy": "开心",
    "sad": "难过",
    "anxious": "焦虑",
    "excited": "兴奋",
    "calm": "平静",
    "frustrated": "沮丧",
    "tired": "疲惫",
    "neutral": "中性",
}

EMOTION_EMOJI = {
    "happy": "😊",
    "sad": "😢",
    "anxious": "😰",
    "excited": "🤩",
    "calm": "😌",
    "frustrated": "😤",
    "tired": "😴",
    "neutral": "😐",
}

EMOTION_SENTIMENT = {
    "happy": 1.0,
    "excited": 1.0,
    "calm": 0.5,
    "neutral": 0.0,
    "tired": -0.5,
    "sad": -1.0,
    "anxious": -1.0,
    "frustrated": -1.0,
}

ANALYSIS_PROMPT = """分析以下对话中用户的情绪状态。

对话历史：
{conversation}

请返回 JSON：
{{
  "current_emotion": "happy|sad|anxious|excited|calm|frustrated|tired|neutral",
  "intensity": 0.0-1.0,
  "trend": "improving|declining|stable|fluctuating",
  "summary": "一句话总结当前情绪状态",
  "triggers": ["触发情绪的事件1", "事件2"]
}}
只返回 JSON。
"""


class EmotionTracker:
    """情绪追踪器"""

    def __init__(self, llm: LLMProvider, memory: MemoryDatabase):
        self.llm = llm
        self.memory = memory

    async def analyze_conversation_emotion(
        self, messages: List[Dict[str, str]]
    ) -> Dict:
        """分析一段对话的情绪"""
        conversation = "\n".join(
            [f"{m['role']}: {m['content']}" for m in messages[-10:]]
        )

        response = await self.llm.chat(
            messages=[ChatMessage(role="user", content=ANALYSIS_PROMPT.format(
                conversation=conversation
            ))],
            temperature=0.2,
            max_tokens=512,
        )

        try:
            content = response.content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()
            return json.loads(content)
        except (json.JSONDecodeError, KeyError):
            return {
                "current_emotion": "neutral",
                "intensity": 0.5,
                "trend": "stable",
                "summary": "无法分析情绪",
                "triggers": [],
            }

    async def get_emotion_timeline(
        self,
        hours: int = 24,
    ) -> List[EmotionRecord]:
        """获取情绪时间线"""
        since = datetime.now() - timedelta(hours=hours)
        return await self.memory.get_emotions(since=since, limit=200)

    async def get_emotion_summary(self, days: int = 7) -> str:
        """获取情绪摘要"""
        since = datetime.now() - timedelta(days=days)
        emotions = await self.memory.get_emotions(since=since, limit=200)

        if not emotions:
            return "最近没有情绪记录"

        # 统计情绪分布
        emotion_counts: Dict[str, int] = {}
        for e in emotions:
            emotion_counts[e.emotion] = emotion_counts.get(e.emotion, 0) + 1

        total = len(emotions)
        lines = [f"过去{days}天的情绪概览（共{total}条记录）："]
        for emotion, count in sorted(emotion_counts.items(), key=lambda x: -x[1]):
            emoji = EMOTION_EMOJI.get(emotion, "❓")
            label = EMOTION_LABELS.get(emotion, emotion)
            pct = count / total * 100
            lines.append(f"  {emoji} {label}: {count}次 ({pct:.0f}%)")

        # 趋势
        if len(emotions) >= 4:
            half = len(emotions) // 2
            recent = emotions[:half]
            older = emotions[half:]
            recent_avg = sum(EMOTION_SENTIMENT.get(e.emotion, 0) for e in recent) / len(recent)
            older_avg = sum(EMOTION_SENTIMENT.get(e.emotion, 0) for e in older) / len(older)

            if recent_avg > older_avg + 0.2:
                lines.append("\n📈 整体情绪在好转！")
            elif recent_avg < older_avg - 0.2:
                lines.append("\n📉 最近情绪有些低落，要注意休息哦")
            else:
                lines.append("\n➡️ 情绪比较稳定")

        return "\n".join(lines)
