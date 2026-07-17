"""Embedding 持久化缓存

将 embedding 向量存储到 SQLite，避免重复调用 LLM embed。
首次计算后缓存，后续直接从 DB 读取。
"""

import json
import logging
import struct
import uuid
from datetime import datetime
from typing import List, Optional, Tuple

from src.llm.base import LLMProvider
from src.memory.database import MemoryDatabase

logger = logging.getLogger(__name__)


class EmbeddingCache:
    """Embedding 缓存层，持久化到 embeddings 表"""

    def __init__(self, llm: LLMProvider, memory: MemoryDatabase):
        self.llm = llm
        self.memory = memory

    async def get_or_compute(
        self, entity_id: str, entity_type: str, content: str
    ) -> List[float]:
        """获取 embedding：有缓存就读缓存，没有就计算并存储

        Args:
            entity_id: 实体 ID（消息 ID 或事实 ID）
            entity_type: 实体类型（"message" 或 "fact"）
            content: 文本内容（用于 embedding 计算）

        Returns:
            embedding 向量
        """
        # 1. 尝试从缓存读取
        cached = await self.get_cached(entity_id, entity_type)
        if cached is not None:
            return cached

        # 2. 缓存未命中，调用 LLM 计算
        embedding = await self.llm.embed(content)

        # 3. 存储到数据库
        await self._save(entity_id, entity_type, content, embedding)

        return embedding

    async def get_cached(
        self, entity_id: str, entity_type: str
    ) -> Optional[List[float]]:
        """从缓存获取 embedding，不存在返回 None"""
        cursor = await self.memory._db.execute(
            "SELECT embedding FROM embeddings WHERE entity_id = ? AND entity_type = ?",
            (entity_id, entity_type),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._deserialize(row["embedding"])

    async def get_all_by_type(
        self, entity_type: str
    ) -> List[Tuple[str, List[float]]]:
        """获取某类型的所有缓存 embedding

        Returns:
            [(entity_id, embedding), ...] 列表
        """
        cursor = await self.memory._db.execute(
            "SELECT entity_id, embedding FROM embeddings WHERE entity_type = ?",
            (entity_type,),
        )
        rows = await cursor.fetchall()
        return [
            (row["entity_id"], self._deserialize(row["embedding"]))
            for row in rows
        ]

    async def _save(
        self,
        entity_id: str,
        entity_type: str,
        content: str,
        embedding: List[float],
    ) -> None:
        """存储 embedding 到数据库"""
        emb_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        blob = self._serialize(embedding)

        await self.memory._db.execute(
            """INSERT OR REPLACE INTO embeddings
               (id, entity_id, entity_type, content, embedding, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (emb_id, entity_id, entity_type, content, blob, now),
        )
        await self.memory._db.commit()

    @staticmethod
    def _serialize(embedding: List[float]) -> bytes:
        """将 embedding 向量序列化为 bytes（float32）"""
        return struct.pack(f"{len(embedding)}f", *embedding)

    @staticmethod
    def _deserialize(blob: bytes) -> List[float]:
        """将 bytes 反序列化为 embedding 向量"""
        n = len(blob) // 4  # float32 = 4 bytes
        return list(struct.unpack(f"{n}f", blob))

    @staticmethod
    def _cosine_similarity(a: List[float], b: List[float]) -> float:
        """计算余弦相似度"""
        if len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
