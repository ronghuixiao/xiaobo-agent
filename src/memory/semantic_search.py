"""历史对话语义检索

使用向量嵌入实现语义级搜索。
当用户的查询与历史对话语义相似时，能主动关联并提醒。
"""

import logging
from datetime import datetime
from typing import List, Optional, Tuple

from src.llm.base import LLMProvider
from src.memory.base import ConversationMessage, ExtractedFact
from src.memory.database import MemoryDatabase

logger = logging.getLogger(__name__)


class SemanticSearch:
    """语义检索器"""

    def __init__(self, llm: LLMProvider, memory: MemoryDatabase):
        self.llm = llm
        self.memory = memory
        self._cache = {}  # 简单缓存: message_id -> embedding

    async def _get_embedding(self, text: str) -> List[float]:
        """获取文本嵌入"""
        return await self.llm.embed(text)

    async def _get_cached_embedding(self, msg: ConversationMessage) -> List[float]:
        """获取缓存的嵌入"""
        if msg.id not in self._cache:
            self._cache[msg.id] = await self._get_embedding(msg.content)
        return self._cache[msg.id]

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

    async def search_similar_messages(
        self,
        query: str,
        limit: int = 5,
        threshold: float = 0.5,
    ) -> List[Tuple[ConversationMessage, float]]:
        """语义搜索相似消息"""
        query_embedding = await self._get_embedding(query)

        # 获取所有用户消息（用于对比）
        all_messages = await self.memory.get_messages(limit=500)
        user_messages = [m for m in all_messages if m.role == "user"]

        if not user_messages:
            return []

        # 计算相似度
        scored = []
        for msg in user_messages:
            msg_embedding = await self._get_cached_embedding(msg)
            similarity = self._cosine_similarity(query_embedding, msg_embedding)
            if similarity >= threshold:
                scored.append((msg, similarity))

        # 按相似度排序
        scored.sort(key=lambda x: -x[1])
        return scored[:limit]

    async def find_related_facts(
        self,
        query: str,
        limit: int = 5,
    ) -> List[ExtractedFact]:
        """查找相关事实"""
        # 先用关键词搜索
        keyword_facts = await self.memory.search_facts(query, limit=limit)

        # 如果关键词搜索结果不够，用语义搜索
        if len(keyword_facts) < limit:
            all_facts = await self.memory.get_facts(limit=100)
            query_embedding = await self._get_embedding(query)

            for fact in all_facts:
                if fact.id in [f.id for f in keyword_facts]:
                    continue
                fact_embedding = await self._get_embedding(fact.content)
                similarity = self._cosine_similarity(query_embedding, fact_embedding)
                if similarity >= 0.4:
                    keyword_facts.append(fact)
                    if len(keyword_facts) >= limit:
                        break

        return keyword_facts[:limit]
