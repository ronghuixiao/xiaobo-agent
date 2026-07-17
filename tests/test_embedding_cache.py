"""测试 EmbeddingCache — embedding 持久化缓存"""
import pytest
import math
from unittest.mock import AsyncMock


def _vec_close(a, b, tol=1e-5):
    """向量近似比较"""
    return len(a) == len(b) and all(
        abs(x - y) < tol for x, y in zip(a, b)
    )


class TestEmbeddingCache:
    """测试 embedding 缓存的存取"""

    @pytest.fixture
    def mock_llm(self):
        llm = AsyncMock()
        llm.embed = AsyncMock(return_value=[0.1, 0.2, 0.3])
        return llm

    @pytest.fixture
    def mock_memory(self, tmp_path):
        import asyncio
        from src.memory.database import MemoryDatabase

        db = MemoryDatabase(str(tmp_path / "test.db"))
        asyncio.get_event_loop().run_until_complete(db.initialize())
        return db

    @pytest.mark.asyncio
    async def test_get_or_compute_returns_same_embedding(self, mock_llm, mock_memory):
        """同一条消息第二次获取应该返回缓存值"""
        from src.memory.embedding_cache import EmbeddingCache

        cache = EmbeddingCache(mock_llm, mock_memory)

        emb1 = await cache.get_or_compute("msg-1", "message", "你好")
        assert _vec_close(emb1, [0.1, 0.2, 0.3])
        assert mock_llm.embed.call_count == 1

        # 第二次：从缓存读取，不再调用 LLM
        emb2 = await cache.get_or_compute("msg-1", "message", "你好")
        assert _vec_close(emb2, [0.1, 0.2, 0.3])
        assert mock_llm.embed.call_count == 1

    @pytest.mark.asyncio
    async def test_different_entities_get_different_embeddings(self, mock_llm, mock_memory):
        """不同消息返回各自的 embedding"""
        from src.memory.embedding_cache import EmbeddingCache

        mock_llm.embed.side_effect = [
            [0.1, 0.2, 0.3],
            [0.4, 0.5, 0.6],
        ]
        cache = EmbeddingCache(mock_llm, mock_memory)

        emb1 = await cache.get_or_compute("msg-1", "message", "你好")
        emb2 = await cache.get_or_compute("msg-2", "message", "再见")

        assert _vec_close(emb1, [0.1, 0.2, 0.3])
        assert _vec_close(emb2, [0.4, 0.5, 0.6])
        assert mock_llm.embed.call_count == 2

    @pytest.mark.asyncio
    async def test_persistence_across_instances(self, mock_llm, mock_memory):
        """缓存应该持久化到数据库，新实例能读到"""
        from src.memory.embedding_cache import EmbeddingCache

        cache1 = EmbeddingCache(mock_llm, mock_memory)
        await cache1.get_or_compute("msg-1", "message", "你好")

        # 新实例：从数据库读取
        mock_llm.embed.reset_mock()
        cache2 = EmbeddingCache(mock_llm, mock_memory)
        emb = await cache2.get_or_compute("msg-1", "message", "你好")

        assert _vec_close(emb, [0.1, 0.2, 0.3])
        mock_llm.embed.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_cached_returns_none_if_not_exists(self, mock_llm, mock_memory):
        """未缓存的 entity 返回 None"""
        from src.memory.embedding_cache import EmbeddingCache

        cache = EmbeddingCache(mock_llm, mock_memory)
        result = await cache.get_cached("msg-999", "message")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_all_by_type(self, mock_llm, mock_memory):
        """按类型获取所有缓存的 embedding"""
        from src.memory.embedding_cache import EmbeddingCache

        mock_llm.embed.side_effect = [
            [0.1, 0.2, 0.3],
            [0.4, 0.5, 0.6],
        ]
        cache = EmbeddingCache(mock_llm, mock_memory)

        await cache.get_or_compute("msg-1", "message", "你好")
        await cache.get_or_compute("fact-1", "fact", "喜欢荔枝味汽水")

        messages = await cache.get_all_by_type("message")
        facts = await cache.get_all_by_type("fact")

        assert len(messages) == 1
        assert messages[0][0] == "msg-1"
        assert _vec_close(messages[0][1], [0.1, 0.2, 0.3])
        assert len(facts) == 1
        assert facts[0][0] == "fact-1"
        assert _vec_close(facts[0][1], [0.4, 0.5, 0.6])
