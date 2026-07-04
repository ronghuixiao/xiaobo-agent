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

CREATE INDEX IF NOT EXISTS idx_conv_session ON conversations(session_id);
CREATE INDEX IF NOT EXISTS idx_conv_timestamp ON conversations(timestamp);
CREATE INDEX IF NOT EXISTS idx_conv_role ON conversations(role);
CREATE INDEX IF NOT EXISTS idx_facts_type ON facts(fact_type);
CREATE INDEX IF NOT EXISTS idx_facts_subject ON facts(subject);
CREATE INDEX IF NOT EXISTS idx_facts_active ON facts(is_active);
CREATE INDEX IF NOT EXISTS idx_emotions_timestamp ON emotions(timestamp);
CREATE INDEX IF NOT EXISTS idx_assoc_keyword ON associations(keyword);
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

        return list(reversed(messages))  # 返回时间正序

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
        """保存提取的事实"""
        await self._db.execute(
            """INSERT INTO facts
               (id, fact_type, subject, content, confidence, source_message_id,
                created_at, updated_at, is_active)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                fact.id,
                fact.fact_type,
                fact.subject,
                fact.content,
                fact.confidence,
                fact.source_message_id,
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
        for table in ["conversations", "facts", "emotions", "associations"]:
            cursor = await self._db.execute(f"SELECT COUNT(*) as cnt FROM {table}")
            row = await cursor.fetchone()
            stats[table] = row["cnt"]
        return stats
