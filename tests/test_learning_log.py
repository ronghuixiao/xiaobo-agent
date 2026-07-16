"""Step 3 测试：学习记录结构化 - learning_log 表"""

import pytest
import uuid
from datetime import datetime


class TestLearningLogTable:
    """测试 learning_log 表"""

    @pytest.fixture
    def db(self, tmp_path):
        """创建测试数据库"""
        import sys
        sys.path.insert(0, str(tmp_path.parent.parent))
        from src.memory.database import MemoryDatabase
        db_path = tmp_path / "test_memory.db"
        return MemoryDatabase(str(db_path))

    @pytest.mark.asyncio
    async def test_table_exists(self, db):
        """learning_log 表必须存在"""
        import aiosqlite
        await db.initialize()
        async with aiosqlite.connect(str(db.db_path)) as conn:
            cursor = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='learning_log'"
            )
            row = await cursor.fetchone()
            assert row is not None, "learning_log 表不存在"

    @pytest.mark.asyncio
    async def test_save_learning_record(self, db):
        """保存学习记录"""
        await db.initialize()
        record = {
            "id": str(uuid.uuid4()),
            "topic": "反向传播",
            "content": "学习了反向传播的数学推导，理解了链式法则",
            "understanding": "基本理解，推导过程有点绕",
            "related_topics": "前向传播,梯度下降",
            "tags": "深度学习,神经网络",
            "source_message_id": None,
            "created_at": datetime.now().isoformat(),
        }
        await db.save_learning_record(record)

        # 验证保存成功
        records = await db.get_learning_records(limit=10)
        assert len(records) >= 1
        assert records[0]["topic"] == "反向传播"

    @pytest.mark.asyncio
    async def test_get_learning_records_by_topic(self, db):
        """按主题查询学习记录"""
        await db.initialize()
        # 保存两条记录
        await db.save_learning_record({
            "id": str(uuid.uuid4()),
            "topic": "设计模式",
            "content": "学习了策略模式",
            "understanding": "理解了",
            "related_topics": "单例模式",
            "tags": "设计模式",
            "created_at": datetime.now().isoformat(),
        })
        await db.save_learning_record({
            "id": str(uuid.uuid4()),
            "topic": "数据结构",
            "content": "学习了二叉树",
            "understanding": "理解了",
            "related_topics": "链表",
            "tags": "数据结构",
            "created_at": datetime.now().isoformat(),
        })

        records = await db.get_learning_records_by_topic("设计模式")
        assert len(records) == 1
        assert records[0]["topic"] == "设计模式"

    @pytest.mark.asyncio
    async def test_get_learning_records_limit(self, db):
        """限制返回数量"""
        await db.initialize()
        for i in range(5):
            await db.save_learning_record({
                "id": str(uuid.uuid4()),
                "topic": f"主题{i}",
                "content": f"内容{i}",
                "understanding": "理解了",
                "related_topics": "",
                "tags": "",
                "created_at": datetime.now().isoformat(),
            })

        records = await db.get_learning_records(limit=3)
        assert len(records) == 3

    @pytest.mark.asyncio
    async def test_delete_learning_record(self, db):
        """删除学习记录"""
        await db.initialize()
        record_id = str(uuid.uuid4())
        await db.save_learning_record({
            "id": record_id,
            "topic": "要删除的",
            "content": "内容",
            "understanding": "理解了",
            "related_topics": "",
            "tags": "",
            "created_at": datetime.now().isoformat(),
        })

        await db.delete_learning_record(record_id)
        records = await db.get_learning_records(limit=10)
        assert all(r["id"] != record_id for r in records)
