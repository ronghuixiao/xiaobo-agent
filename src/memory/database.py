"""记忆数据库 - SQLite 持久化存储

使用 SQLite 存储所有记忆数据。
支持 FTS5 全文检索（Phase 2 用）。
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosqlite

from .base import (
    AssociationIndex,
    ConversationMessage,
    EmotionRecord,
    ExtractedFact,
)

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    emotion TEXT,
    topics TEXT DEFAULT '[]',
    metadata TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS facts (
    id TEXT PRIMARY KEY,
    fact_type TEXT NOT NULL,
    subject TEXT NOT NULL,
    content TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    source_message_id TEXT,
    event_time TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    is_active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS emotions (
    id TEXT PRIMARY KEY,
    emotion TEXT NOT NULL,
    intensity REAL DEFAULT 0.5,
    context TEXT DEFAULT '',
    source_message_id TEXT,
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS associations (
    id TEXT PRIMARY KEY,
    keyword TEXT NOT NULL,
    message_ids TEXT DEFAULT '[]',
    fact_ids TEXT DEFAULT '[]',
    last_updated TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    date TEXT NOT NULL,
    time TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',
    type TEXT DEFAULT 'user',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_conv_session ON conversations(session_id);
CREATE INDEX IF NOT EXISTS idx_conv_timestamp ON conversations(timestamp);
CREATE INDEX IF NOT EXISTS idx_conv_role ON conversations(role);
CREATE INDEX IF NOT EXISTS idx_facts_type ON facts(fact_type);
CREATE INDEX IF NOT EXISTS idx_facts_subject ON facts(subject);
CREATE INDEX IF NOT EXISTS idx_facts_active ON facts(is_active);
CREATE INDEX IF NOT EXISTS idx_emotions_timestamp ON emotions(timestamp);
CREATE INDEX IF NOT EXISTS idx_assoc_keyword ON associations(keyword);

CREATE TABLE IF NOT EXISTS summaries (
    id TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    type TEXT NOT NULL,
    content TEXT NOT NULL,
    message_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_summaries_date ON summaries(date);
CREATE INDEX IF NOT EXISTS idx_summaries_type ON summaries(type);

CREATE TABLE IF NOT EXISTS embeddings (
    id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding BLOB NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_embeddings_entity ON embeddings(entity_id);
CREATE INDEX IF NOT EXISTS idx_embeddings_type ON embeddings(entity_type);

CREATE TABLE IF NOT EXISTS learning_log (
    id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    content TEXT NOT NULL,
    understanding TEXT DEFAULT '',
    related_topics TEXT DEFAULT '',
    tags TEXT DEFAULT '',
    source_message_id TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_learning_topic ON learning_log(topic);
CREATE INDEX IF NOT EXISTS idx_learning_created ON learning_log(created_at);
"""


class MemoryDatabase:
    """记忆数据库操作层"""

    def __init__(self, db_path: str = "~/.xiaobo-agent/memory.db"):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db: Optional[aiosqlite.Connection] = None

    async def initialize(self):
        """初始化数据库"""
        self._db = await aiosqlite.connect(str(self.db_path))
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(SCHEMA)
        await self._db.commit()
        logger.info(f"记忆数据库已初始化: {self.db_path}")

    async def close(self):
        """关闭数据库连接"""
        if self._db:
            await self._db.close()

    # ---- Layer 0: 对话存档 ----

    async def save_message(self, msg: ConversationMessage) -> str:
        """保存一条对话消息"""
        await self._db.execute(
            """INSERT INTO conversations
               (id, session_id, role, content, timestamp, emotion, topics, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                msg.id,
                msg.session_id,
                msg.role,
                msg.content,
                msg.timestamp.isoformat(),
                msg.emotion,
                json.dumps(msg.topics, ensure_ascii=False),
                json.dumps(msg.metadata, ensure_ascii=False),
            ),
        )
        await self._db.commit()
        return msg.id

    async def get_messages(
        self,
        session_id: Optional[str] = None,
        limit: int = 50,
        before: Optional[datetime] = None,
    ) -> List[ConversationMessage]:
        """获取对话消息"""
        query = "SELECT * FROM conversations"
        params: List[Any] = []
        conditions = []

        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)
        if before:
            conditions.append("timestamp < ?")
            params.append(before.isoformat())

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        cursor = await self._db.execute(query, params)
        rows = await cursor.fetchall()

        messages = []
        for row in rows:
            messages.append(ConversationMessage(
                id=row["id"],
                session_id=row["session_id"],
                role=row["role"],
                content=row["content"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                emotion=row["emotion"],
                topics=json.loads(row["topics"]),
                metadata=json.loads(row["metadata"]),
            ))

        return messages  # 返回时间倒序（最新在前）

    async def search_messages(self, keyword: str, limit: int = 20) -> List[ConversationMessage]:
        """关键词搜索对话消息"""
        cursor = await self._db.execute(
            "SELECT * FROM conversations WHERE content LIKE ? ORDER BY timestamp DESC LIMIT ?",
            (f"%{keyword}%", limit),
        )
        rows = await cursor.fetchall()

        return [
            ConversationMessage(
                id=row["id"],
                session_id=row["session_id"],
                role=row["role"],
                content=row["content"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                emotion=row["emotion"],
                topics=json.loads(row["topics"]),
                metadata=json.loads(row["metadata"]),
            )
            for row in rows
        ]

    # ---- Layer 1: 事实存储 ----

    async def save_fact(self, fact: ExtractedFact) -> str:
        """保存提取的事实（upsert：同 subject+fact_type 更新，否则插入）"""
        # 检查是否已存在同 subject+fact_type 的事实
        cursor = await self._db.execute(
            "SELECT id FROM facts WHERE subject = ? AND fact_type = ? LIMIT 1",
            (fact.subject, fact.fact_type),
        )
        existing = await cursor.fetchone()

        if existing:
            # 更新旧记录
            await self._db.execute(
                """UPDATE facts SET
                   content = ?, confidence = ?, event_time = ?,
                   updated_at = ?
                   WHERE id = ?""",
                (
                    fact.content,
                    fact.confidence,
                    fact.event_time,
                    fact.updated_at.isoformat(),
                    existing["id"],
                ),
            )
            await self._db.commit()
            return existing["id"]
        else:
            # 插入新记录
            await self._db.execute(
                """INSERT INTO facts
                   (id, fact_type, subject, content, confidence, source_message_id,
                    event_time, created_at, updated_at, is_active)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    fact.id,
                    fact.fact_type,
                    fact.subject,
                    fact.content,
                    fact.confidence,
                    fact.source_message_id,
                    fact.event_time,
                    fact.created_at.isoformat(),
                    fact.updated_at.isoformat(),
                    int(fact.is_active),
                ),
            )
            await self._db.commit()
            return fact.id

    async def get_facts(
        self,
        fact_type: Optional[str] = None,
        subject: Optional[str] = None,
        active_only: bool = True,
        limit: int = 100,
    ) -> List[ExtractedFact]:
        """获取事实"""
        query = "SELECT * FROM facts"
        params: List[Any] = []
        conditions = []

        if fact_type:
            conditions.append("fact_type = ?")
            params.append(fact_type)
        if subject:
            conditions.append("subject LIKE ?")
            params.append(f"%{subject}%")
        if active_only:
            conditions.append("is_active = 1")

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)

        cursor = await self._db.execute(query, params)
        rows = await cursor.fetchall()

        return [
            ExtractedFact(
                id=row["id"],
                fact_type=row["fact_type"],
                subject=row["subject"],
                content=row["content"],
                confidence=row["confidence"],
                source_message_id=row["source_message_id"],
                event_time=row["event_time"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
                is_active=bool(row["is_active"]),
            )
            for row in rows
        ]

    async def search_facts(self, keyword: str, limit: int = 20) -> List[ExtractedFact]:
        """关键词搜索事实"""
        cursor = await self._db.execute(
            "SELECT * FROM facts WHERE content LIKE ? OR subject LIKE ? ORDER BY updated_at DESC LIMIT ?",
            (f"%{keyword}%", f"%{keyword}%", limit),
        )
        rows = await cursor.fetchall()

        return [
            ExtractedFact(
                id=row["id"],
                fact_type=row["fact_type"],
                subject=row["subject"],
                content=row["content"],
                confidence=row["confidence"],
                source_message_id=row["source_message_id"],
                event_time=row["event_time"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
                is_active=bool(row["is_active"]),
            )
            for row in rows
        ]

    # ---- Layer 2: 情绪记录 ----

    async def save_emotion(self, record: EmotionRecord) -> str:
        """保存情绪记录"""
        await self._db.execute(
            """INSERT INTO emotions
               (id, emotion, intensity, context, source_message_id, timestamp)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                record.id,
                record.emotion,
                record.intensity,
                record.context,
                record.source_message_id,
                record.timestamp.isoformat(),
            ),
        )
        await self._db.commit()
        return record.id

    async def get_emotions(
        self,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[EmotionRecord]:
        """获取情绪记录"""
        query = "SELECT * FROM emotions"
        params: List[Any] = []

        if since:
            query += " WHERE timestamp >= ?"
            params.append(since.isoformat())

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        cursor = await self._db.execute(query, params)
        rows = await cursor.fetchall()

        return [
            EmotionRecord(
                id=row["id"],
                emotion=row["emotion"],
                intensity=row["intensity"],
                context=row["context"],
                source_message_id=row["source_message_id"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
            )
            for row in rows
        ]

    # ---- Layer 3: 关联索引 ----

    async def save_association(self, assoc: AssociationIndex) -> str:
        """保存关联索引"""
        # Upsert: 如果关键词已存在，合并 message_ids
        cursor = await self._db.execute(
            "SELECT id, message_ids, fact_ids FROM associations WHERE keyword = ?",
            (assoc.keyword,),
        )
        existing = await cursor.fetchone()

        if existing:
            old_msg_ids = json.loads(existing["message_ids"])
            old_fact_ids = json.loads(existing["fact_ids"])
            merged_msg_ids = list(set(old_msg_ids + assoc.message_ids))
            merged_fact_ids = list(set(old_fact_ids + assoc.fact_ids))
            await self._db.execute(
                "UPDATE associations SET message_ids = ?, fact_ids = ?, last_updated = ? WHERE id = ?",
                (
                    json.dumps(merged_msg_ids),
                    json.dumps(merged_fact_ids),
                    datetime.now().isoformat(),
                    existing["id"],
                ),
            )
        else:
            await self._db.execute(
                """INSERT INTO associations
                   (id, keyword, message_ids, fact_ids, last_updated)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    assoc.id,
                    assoc.keyword,
                    json.dumps(assoc.message_ids, ensure_ascii=False),
                    json.dumps(assoc.fact_ids, ensure_ascii=False),
                    assoc.last_updated.isoformat(),
                ),
            )

        await self._db.commit()
        return assoc.id

    async def get_associations(self, keyword: str) -> List[AssociationIndex]:
        """获取关键词的关联"""
        cursor = await self._db.execute(
            "SELECT * FROM associations WHERE keyword = ?",
            (keyword,),
        )
        rows = await cursor.fetchall()

        return [
            AssociationIndex(
                id=row["id"],
                keyword=row["keyword"],
                message_ids=json.loads(row["message_ids"]),
                fact_ids=json.loads(row["fact_ids"]),
                last_updated=datetime.fromisoformat(row["last_updated"]),
            )
            for row in rows
        ]

    # ---- 统计 ----

    async def get_stats(self) -> Dict[str, Any]:
        """获取记忆统计"""
        stats = {}
        for table in ["conversations", "facts", "emotions", "associations", "tasks"]:
            cursor = await self._db.execute(f"SELECT COUNT(*) as cnt FROM {table}")
            row = await cursor.fetchone()
            stats[table] = row["cnt"]
        return stats

    # ---- Layer 4: 任务管理 ----

    async def save_task(
        self,
        title: str,
        date_str: str,
        time_str: str = "",
        task_type: str = "user",
        task_id: Optional[str] = None,
        status: str = "pending",
    ) -> str:
        """保存任务，返回任务 ID"""
        import uuid
        if task_id is None:
            task_id = f"task-{str(uuid.uuid4())[:8]}"
        await self._db.execute(
            """INSERT OR REPLACE INTO tasks
               (id, title, date, time, status, type, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (task_id, title, date_str, time_str, status, task_type, datetime.now().isoformat()),
        )
        await self._db.commit()
        return task_id

    async def create_task(
        self,
        title: str,
        date_str: str = "",
        time_str: str = "",
        task_type: str = "user",
    ) -> str:
        """创建任务（自动生成 ID）"""
        if not date_str:
            date_str = datetime.now().strftime("%Y-%m-%d")
        import uuid
        task_id = f"task-{str(uuid.uuid4())[:8]}"
        return await self.save_task(
            title=title,
            date_str=date_str,
            time_str=time_str,
            task_type=task_type,
            task_id=task_id,
        )

    async def get_tasks_for_date(
        self,
        date_str: str,
        task_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """获取指定日期的任务"""
        if task_type:
            cursor = await self._db.execute(
                "SELECT * FROM tasks WHERE date = ? AND type = ? ORDER BY time",
                (date_str, task_type),
            )
        else:
            cursor = await self._db.execute(
                "SELECT * FROM tasks WHERE date = ? ORDER BY time",
                (date_str,),
            )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_today_tasks(self) -> List[Dict[str, Any]]:
        """获取今日任务"""
        today = datetime.now().strftime("%Y-%m-%d")
        return await self.get_tasks_for_date(today)

    async def get_all_tasks(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取所有任务（按日期倒序）"""
        cursor = await self._db.execute(
            "SELECT * FROM tasks ORDER BY date DESC, time LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_pending_tasks_with_time(self, date_str: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取有时间的待办任务"""
        if date_str is None:
            date_str = datetime.now().strftime("%Y-%m-%d")
        cursor = await self._db.execute(
            """SELECT * FROM tasks
               WHERE date <= ? AND status = 'pending'
               AND time != '' AND time IS NOT NULL
               ORDER BY date, time""",
            (date_str,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def update_task_status(self, task_id: str, status: str) -> None:
        """更新任务状态"""
        await self._db.execute(
            "UPDATE tasks SET status = ? WHERE id = ?",
            (status, task_id),
        )
        await self._db.commit()

    async def move_pending_tasks(self, from_date: str, to_date: str) -> int:
        """将指定日期的待办任务移动到另一个日期"""
        cursor = await self._db.execute(
            "UPDATE tasks SET date = ? WHERE date = ? AND status = 'pending'",
            (to_date, from_date),
        )
        count = cursor.rowcount
        await self._db.commit()
        return count

    async def mark_done_by_prefix(self, prefix: str) -> None:
        """按前缀标记任务完成"""
        today = datetime.now().strftime("%Y-%m-%d")
        cursor = await self._db.execute(
            "SELECT id FROM tasks WHERE id LIKE ? AND date = ? AND status = 'pending'",
            (prefix + "%", today),
        )
        rows = await cursor.fetchall()
        for row in rows:
            await self._db.execute(
                "UPDATE tasks SET status = 'done' WHERE id = ?",
                (row["id"],),
            )
        await self._db.commit()

    # ==================== 学习记录 ====================

    async def save_learning_record(self, record: Dict[str, Any]) -> None:
        """保存学习记录"""
        await self._db.execute(
            """INSERT OR REPLACE INTO learning_log
               (id, topic, content, understanding, related_topics, tags,
                source_message_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record["id"],
                record["topic"],
                record["content"],
                record.get("understanding", ""),
                record.get("related_topics", ""),
                record.get("tags", ""),
                record.get("source_message_id"),
                record["created_at"],
            ),
        )
        await self._db.commit()

    async def get_learning_records(
        self, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """获取学习记录，按时间倒序"""
        cursor = await self._db.execute(
            "SELECT * FROM learning_log ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_learning_records_by_topic(
        self, topic: str
    ) -> List[Dict[str, Any]]:
        """按主题查询学习记录"""
        cursor = await self._db.execute(
            "SELECT * FROM learning_log WHERE topic = ? ORDER BY created_at DESC",
            (topic,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def delete_learning_record(self, record_id: str) -> None:
        """删除学习记录"""
        await self._db.execute(
            "DELETE FROM learning_log WHERE id = ?",
            (record_id,),
        )
        await self._db.commit()
