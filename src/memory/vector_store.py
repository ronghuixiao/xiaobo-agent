"""向量存储

使用 SQLite 存储嵌入向量，支持高效的语义搜索。
"""
import json
import logging
import struct
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from src.memory.database import MemoryDatabase

logger = logging.getLogger(__name__)


class VectorStore:
    """向量存储"""

    def __init__(self, db: MemoryDatabase):
        self.db = db

    @staticmethod
    def _serialize_embedding(embedding: List[float]) -> bytes:
        """将嵌入向量序列化为字节"""
        return struct.pack(f'{len(embedding)}f', *embedding)

    @staticmethod
    def _deserialize_embedding(data: bytes) -> List[float]:
        """将字节反序列化为嵌入向量"""
        count = len(data) // 4  # float 是 4 字节
        return list(struct.unpack(f'{count}f', data))

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

    async def save_embedding(
        self,
        entity_id: str,
        entity_type: str,
        content: str,
        embedding: List[float]
    ) -> str:
        """保存嵌入向量"""
        embedding_id = f"emb-{entity_id}"
        serialized = self._serialize_embedding(embedding)

        await self.db._db.execute("""
            INSERT OR REPLACE INTO embeddings (id, entity_id, entity_type, content, embedding, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (embedding_id, entity_id, entity_type, content, serialized, datetime.now().isoformat()))
        await self.db._db.commit()

        return embedding_id

    async def get_embedding(self, entity_id: str) -> Optional[List[float]]:
        """获取嵌入向量"""
        cursor = await self.db._db.execute(
            "SELECT embedding FROM embeddings WHERE entity_id = ?",
            (entity_id,)
        )
        row = await cursor.fetchone()
        if row:
            return self._deserialize_embedding(row["embedding"])
        return None

    async def search_similar(
        self,
        query_embedding: List[float],
        limit: int = 5,
        threshold: float = 0.5,
        entity_type: Optional[str] = None
    ) -> List[Dict]:
        """搜索相似内容"""
        if entity_type:
            cursor = await self.db._db.execute(
                "SELECT entity_id, entity_type, content, embedding FROM embeddings WHERE entity_type = ?",
                (entity_type,)
            )
        else:
            cursor = await self.db._db.execute(
                "SELECT entity_id, entity_type, content, embedding FROM embeddings"
            )

        rows = await cursor.fetchall()
        results = []

        for row in rows:
            embedding = self._deserialize_embedding(row["embedding"])
            similarity = self._cosine_similarity(query_embedding, embedding)
            if similarity >= threshold:
                results.append({
                    "entity_id": row["entity_id"],
                    "entity_type": row["entity_type"],
                    "content": row["content"],
                    "similarity": similarity,
                })

        results.sort(key=lambda x: -x["similarity"])
        return results[:limit]

    async def batch_save(self, items: List[Tuple[str, str, str, List[float]]]) -> int:
        """批量保存嵌入"""
        count = 0
        for entity_id, entity_type, content, embedding in items:
            await self.save_embedding(entity_id, entity_type, content, embedding)
            count += 1

        logger.info(f"💾 批量保存 {count} 个嵌入向量")
        return count
