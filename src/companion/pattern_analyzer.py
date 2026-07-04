"""模式分析器

分析用户行为模式：
- 每周活跃规律
- 情绪波动周期
- 习惯变化检测
- 使用时间趋势
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import Counter

from src.memory.base import ConversationMessage, EmotionRecord
from src.memory.database import MemoryDatabase

logger = logging.getLogger(__name__)


class PatternAnalyzer:
    """模式分析器"""

    def __init__(self, memory: MemoryDatabase):
        self.memory = memory

    async def analyze_weekly_pattern(self) -> Dict:
        """分析每周模式：哪天最忙、哪天最闲、情绪规律"""
        now = datetime.now()
        week_start = now - timedelta(days=7)

        messages = await self.memory.get_messages(limit=2000)
        week_messages = [m for m in messages if m.timestamp >= week_start]

        # 按星期几分组
        weekday_counts: Dict[str, int] = {
            "周一": 0, "周二": 0, "周三": 0, "周四": 0,
            "周五": 0, "周六": 0, "周日": 0,
        }
        weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

        for m in week_messages:
            wd = weekday_names[m.timestamp.weekday()]
            weekday_counts[wd] += 1

        # 找最忙和最闲
        busiest = max(weekday_counts, key=weekday_counts.get) if any(weekday_counts.values()) else "无数据"
        quietest = min(weekday_counts, key=weekday_counts.get) if any(weekday_counts.values()) else "无数据"

        # 情绪分布
        emotions = await self.memory.get_emotions(since=week_start, limit=500)
        emotion_counts = Counter(e.emotion for e in emotions)

        return {
            "period": f"{week_start.strftime('%m-%d')} ~ {now.strftime('%m-%d')}",
            "total_messages": len(week_messages),
            "weekday_distribution": weekday_counts,
            "busiest_day": busiest,
            "quietest_day": quietest,
            "emotion_distribution": dict(emotion_counts),
            "total_emotions": len(emotions),
        }

    async def detect_habit_changes(self, weeks: int = 4) -> List[str]:
        """检测习惯变化：使用时间增减、新偏好出现"""
        changes = []
        now = datetime.now()

        # 对比最近一周 vs 上一周
        this_week_start = now - timedelta(days=7)
        last_week_start = now - timedelta(days=14)

        this_week_msgs = await self.memory.get_messages(limit=1000)
        this_week = [m for m in this_week_msgs if m.timestamp >= this_week_start]
        last_week = [m for m in this_week_msgs if last_week_start <= m.timestamp < this_week_start]

        # 对话频率变化
        if last_week:
            ratio = len(this_week) / max(len(last_week), 1)
            if ratio > 1.5:
                changes.append(f"📈 本周对话量增加了 {int((ratio-1)*100)}%，互动更频繁了！")
            elif ratio < 0.5:
                changes.append(f"📉 本周对话量减少了 {int((1-ratio)*100)}%，记得多和我聊聊～")

        # 新出现的话题
        this_week_facts = await self.memory.get_facts(limit=200)
        this_week_topics = set(f.subject for f in this_week_facts if f.created_at >= this_week_start)
        last_week_topics = set(f.subject for f in this_week_facts if last_week_start <= f.created_at < this_week_start)
        new_topics = this_week_topics - last_week_topics
        if new_topics:
            changes.append(f"🆕 新话题出现: {', '.join(list(new_topics)[:3])}")

        # 习惯变化
        this_week_emotions = await self.memory.get_emotions(since=this_week_start, limit=200)
        last_week_emotions = await self.memory.get_emotions(since=last_week_start, limit=200)
        last_week_emotions = [e for e in last_week_emotions if e.timestamp < this_week_start]

        if this_week_emotions and last_week_emotions:
            from src.companion.emotion_tracker import EMOTION_SENTIMENT
            this_avg = sum(EMOTION_SENTIMENT.get(e.emotion, 0) for e in this_week_emotions) / len(this_week_emotions)
            last_avg = sum(EMOTION_SENTIMENT.get(e.emotion, 0) for e in last_week_emotions) / len(last_week_emotions)
            if this_avg > last_avg + 0.2:
                changes.append("😊 整体情绪比上周好转了！")
            elif this_avg < last_avg - 0.2:
                changes.append("💙 最近情绪有些波动，要注意休息哦")

        if not changes:
            changes.append("这周的生活模式比较稳定，继续保持～")

        return changes

    async def get_activity_heatmap(self, weeks: int = 4) -> Dict:
        """生成活动热力图数据（按小时和星期）"""
        now = datetime.now()
        start = now - timedelta(weeks=weeks)

        messages = await self.memory.get_messages(limit=5000)
        period_msgs = [m for m in messages if m.timestamp >= start]

        # 初始化 7x24 矩阵
        heatmap = [[0] * 24 for _ in range(7)]
        weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

        for m in period_msgs:
            wd = m.timestamp.weekday()
            hr = m.timestamp.hour
            heatmap[wd][hr] += 1

        return {
            "weeks": weeks,
            "total_messages": len(period_msgs),
            "heatmap": heatmap,
            "weekday_names": weekday_names,
            "peak_hours": self._find_peak_hours(heatmap),
        }

    def _find_peak_hours(self, heatmap: List[List[int]]) -> List[int]:
        """找最活跃的小时"""
        hourly_totals = [sum(heatmap[wd][hr] for wd in range(7)) for hr in range(24)]
        # 返回前 3 个最活跃的小时
        sorted_hours = sorted(range(24), key=lambda h: -hourly_totals[h])
        return sorted_hours[:3]

    async def predict_mood(self) -> Dict:
        """基于历史模式预测今日情绪"""
        now = datetime.now()
        weekday = now.weekday()

        # 查找历史上同星期的情绪
        all_emotions = await self.memory.get_emotions(limit=1000)
        same_weekday = [e for e in all_emotions if e.timestamp.weekday() == weekday]

        if not same_weekday:
            return {
                "prediction": "数据不足，无法预测",
                "confidence": 0,
                "based_on": 0,
            }

        # 统计历史上同星期的情绪分布
        from src.companion.emotion_tracker import EMOTION_SENTIMENT, EMOTION_LABELS, EMOTION_EMOJI
        emotion_counts = Counter(e.emotion for e in same_weekday)
        total = len(same_weekday)

        most_likely = emotion_counts.most_common(1)[0]
        avg_sentiment = sum(EMOTION_SENTIMENT.get(e.emotion, 0) for e in same_weekday) / total

        return {
            "prediction": most_likely[0],
            "prediction_label": EMOTION_LABELS.get(most_likely[0], most_likely[0]),
            "prediction_emoji": EMOTION_EMOJI.get(most_likely[0], "❓"),
            "confidence": most_likely[1] / total,
            "based_on": total,
            "avg_sentiment": avg_sentiment,
            "sentiment_trend": "偏积极" if avg_sentiment > 0.2 else ("偏消极" if avg_sentiment < -0.2 else "中性"),
        }
