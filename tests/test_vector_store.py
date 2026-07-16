"""向量数据库测试"""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock


class TestVectorStore:
    """测试向量存储"""

    def test_vector_store_class_exists(self):
        """向量存储类存在"""
        from src.memory.vector_store import VectorStore
        assert hasattr(VectorStore, 'save_embedding')
        assert hasattr(VectorStore, 'search_similar')
        assert hasattr(VectorStore, 'batch_save')

    @pytest.mark.asyncio
    async def test_save_embedding(self):
        """保存嵌入向量"""
        from src.memory.vector_store import VectorStore
        from src.memory.database import MemoryDatabase

        db = MemoryDatabase(":memory:")
        await db.initialize()

        store = VectorStore(db)
        embedding = [0.1] * 384  # nomic-embed-text 维度

        await store.save_embedding(
            entity_id="msg-123",
            entity_type="message",
            content="测试消息",
            embedding=embedding
        )

        # 验证保存成功
        cursor = await db._db.execute(
            "SELECT * FROM embeddings WHERE entity_id = ?",
            ("msg-123",)
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["entity_type"] == "message"

        await db.close()

    @pytest.mark.asyncio
    async def test_search_similar(self):
        """语义搜索相似内容"""
        from src.memory.vector_store import VectorStore
        from src.memory.database import MemoryDatabase

        db = MemoryDatabase(":memory:")
        await db.initialize()

        store = VectorStore(db)

        # 保存几个嵌入
        await store.save_embedding(
            entity_id="msg-1",
            entity_type="message",
            content="我喜欢吃火锅",
            embedding=[0.1] * 384
        )
        await store.save_embedding(
            entity_id="msg-2",
            entity_type="message",
            content="今天天气真好",
            embedding=[0.2] * 384
        )

        # 搜索相似内容
        results = await store.search_similar(
            query_embedding=[0.1] * 384,
            limit=5,
            threshold=0.0
        )

        assert len(results) >= 1
        assert results[0]["entity_id"] in ["msg-1", "msg-2"]

        await db.close()

    @pytest.mark.asyncio
    async def test_batch_save(self):
        """批量保存嵌入"""
        from src.memory.vector_store import VectorStore
        from src.memory.database import MemoryDatabase

        db = MemoryDatabase(":memory:")
        await db.initialize()

        store = VectorStore(db)

        items = [
            ("msg-1", "message", "消息1", [0.1] * 384),
            ("msg-2", "message", "消息2", [0.2] * 384),
            ("msg-3", "message", "消息3", [0.3] * 384),
        ]

        await store.batch_save(items)

        # 验证保存成功
        cursor = await db._db.execute("SELECT COUNT(*) as cnt FROM embeddings")
        row = await cursor.fetchone()
        assert row["cnt"] == 3

        await db.close()

    @pytest.mark.asyncio
    async def test_get_embedding(self):
        """获取嵌入向量"""
        from src.memory.vector_store import VectorStore
        from src.memory.database import MemoryDatabase

        db = MemoryDatabase(":memory:")
        await db.initialize()

        store = VectorStore(db)
        embedding = [0.1] * 384

        await store.save_embedding(
            entity_id="msg-123",
            entity_type="message",
            content="测试消息",
            embedding=embedding
        )

        result = await store.get_embedding("msg-123")
        assert result is not None
        assert len(result) == 384

        await db.close()
