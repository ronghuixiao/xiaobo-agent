"""每日摘要 API 端点

提供 /api/daily-summary 端点，返回结构化的每日摘要数据，用于可视化。
包括：今日话题、学习记录、情绪时间线、连续摘要、昨日摘要、明日任务。

Usage:
    from src.api.daily_summary import create_daily_summary_router
    app.include_router(create_daily_summary_router(memory=memory))
"""

import json
import re
from collections import Counter
from datetime import datetime, timedelta

from fastapi import APIRouter


def create_daily_summary_router(memory=None) -> APIRouter:
    """创建每日摘要路由

    Args:
        memory: MemoryDatabase 实例（带 _db 属性的 aiosqlite 连接）
    """
    router = APIRouter(tags=["daily-summary"])

    def _today_str():
        return datetime.now().strftime("%Y-%m-%d")

    def _yesterday_str():
        return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    def _tomorrow_str():
        return (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    @router.get("/api/daily-summary")
    async def get_daily_summary():
        """获取今日每日摘要结构化数据"""
        today = _today_str()
        yesterday = _yesterday_str()
        tomorrow = _tomorrow_str()

        result = {
            "today_topics": [],
            "today_learning": [],
            "emotions_timeline": [],
            "summary_text": "",
            "yesterday_summary": "",
            "tomorrow_tasks": [],
        }

        if not memory or not memory._db:
            return result

        db = memory._db

        # === 1. today_topics: 从今日对话中提取关键词话题 ===
        try:
            cursor = await db.execute(
                "SELECT role, content, timestamp FROM conversations "
                "WHERE DATE(timestamp) = ? ORDER BY timestamp",
                (today,),
            )
            today_messages = await cursor.fetchall()

            if today_messages:
                # 提取关键词：简单分词（按标点和空格切分，过滤短词）
                keyword_counter = Counter()
                msg_by_keyword = {}
                for msg in today_messages:
                    content = msg["content"] if msg["content"] else ""
                    # 提取中文词（2字以上）和英文词（3字母以上）
                    words = re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}", content)
                    for w in words:
                        w_lower = w.lower()
                        keyword_counter[w_lower] += 1
                        if w_lower not in msg_by_keyword:
                            msg_by_keyword[w_lower] = []
                        # 只保留前3条相关对话摘要
                        snippet = content[:80] + ("..." if len(content) > 80 else "")
                        if len(msg_by_keyword[w_lower]) < 3:
                            msg_by_keyword[w_lower].append(snippet)

                # 取出现频率最高的前10个关键词
                top_keywords = keyword_counter.most_common(10)
                result["today_topics"] = [
                    {
                        "keyword": kw,
                        "count": count,
                        "related_convos": msg_by_keyword.get(kw, []),
                    }
                    for kw, count in top_keywords
                ]
        except Exception:
            pass

        # === 2. today_learning: 今日学习记录 ===
        try:
            cursor = await db.execute(
                "SELECT topic, tags, understanding, content FROM learning_log "
                "WHERE DATE(created_at) = ? ORDER BY created_at",
                (today,),
            )
            learning_rows = await cursor.fetchall()
            for row in learning_rows:
                tags_str = row["tags"] if row["tags"] else ""
                keywords = [t.strip() for t in tags_str.split(",") if t.strip()]
                result["today_learning"].append(
                    {
                        "topic": row["topic"],
                        "keywords": keywords,
                        "understanding": row["understanding"] if row["understanding"] else "",
                    }
                )
        except Exception:
            pass

        # === 3. emotions_timeline: 今日情绪时间线 ===
        try:
            cursor = await db.execute(
                "SELECT emotion, intensity, context, timestamp FROM emotions "
                "WHERE DATE(timestamp) = ? ORDER BY timestamp",
                (today,),
            )
            emotion_rows = await cursor.fetchall()
            for row in emotion_rows:
                ts = row["timestamp"] if row["timestamp"] else ""
                # 提取时间部分 HH:MM
                time_part = ts.split("T")[1][:5] if "T" in ts else ts.split(" ")[-1][:5] if " " in ts else ts
                result["emotions_timeline"].append(
                    {
                        "time": time_part,
                        "emotion": row["emotion"],
                        "intensity": row["intensity"] if row["intensity"] else 0.5,
                    }
                )
        except Exception:
            pass

        # === 4. summary_text: 连续性摘要 (昨天→今天→明天) ===
        try:
            # 尝试从 summaries 表获取今日摘要
            cursor = await db.execute(
                "SELECT content FROM summaries WHERE date = ? AND type = 'daily' ORDER BY created_at DESC LIMIT 1",
                (today,),
            )
            summary_row = await cursor.fetchone()
            if summary_row and summary_row["content"]:
                result["summary_text"] = summary_row["content"]
            else:
                # 自动生成简单摘要
                parts = []
                if result["today_topics"]:
                    topic_words = [t["keyword"] for t in result["today_topics"][:5]]
                    parts.append(f"今日话题：{'、'.join(topic_words)}")
                if result["today_learning"]:
                    learn_topics = [l["topic"] for l in result["today_learning"]]
                    parts.append(f"学习内容：{'、'.join(learn_topics)}")
                if result["emotions_timeline"]:
                    emotions = [e["emotion"] for e in result["emotions_timeline"]]
                    parts.append(f"情绪变化：{'→'.join(emotions)}")
                if parts:
                    result["summary_text"] = " | ".join(parts)
        except Exception:
            pass

        # === 5. yesterday_summary: 昨日摘要 ===
        try:
            cursor = await db.execute(
                "SELECT content FROM summaries WHERE date = ? AND type = 'daily' ORDER BY created_at DESC LIMIT 1",
                (yesterday,),
            )
            yest_row = await cursor.fetchone()
            if yest_row and yest_row["content"]:
                result["yesterday_summary"] = yest_row["content"]
            else:
                # 从昨日对话生成简要摘要
                cursor2 = await db.execute(
                    "SELECT content FROM conversations WHERE DATE(timestamp) = ? AND role = 'user' LIMIT 5",
                    (yesterday,),
                )
                yest_msgs = await cursor2.fetchall()
                if yest_msgs:
                    snippets = [m["content"][:60] for m in yest_msgs if m["content"]]
                    result["yesterday_summary"] = f"昨日对话摘要：{'；'.join(snippets)}" if snippets else ""
        except Exception:
            pass

        # === 6. tomorrow_tasks: 明日任务 ===
        try:
            cursor = await db.execute(
                "SELECT id, title, time, status, type FROM tasks WHERE date = ? ORDER BY time",
                (tomorrow,),
            )
            task_rows = await cursor.fetchall()
            for row in task_rows:
                result["tomorrow_tasks"].append(
                    {
                        "id": row["id"],
                        "title": row["title"],
                        "time": row["time"] if row["time"] else "",
                        "status": row["status"] if row["status"] else "pending",
                        "type": row["type"] if row["type"] else "user",
                    }
                )
        except Exception:
            pass

        return result

    return router
