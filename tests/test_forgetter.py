"""遗忘机制测试"""
import pytest
from datetime import datetime, timedelta


class TestForgetter:
    """测试遗忘管理器"""

    def test_forgetter_class_exists(self):
        """遗忘管理器类存在"""
        from src.memory.forgetter import Forgetter
        assert hasattr(Forgetter, 'forget_old_facts')
        assert hasattr(Forgetter, 'deduplicate_facts')
        assert hasattr(Forgetter, 'cleanup_low_confidence')

    @pytest.mark.asyncio
    async def test_forget_old_facts_marks_inactive(self):
        """超过天数的事实被标记为inactive"""
        from src.memory.forgetter import Forgetter
        from src.memory.database import MemoryDatabase
        from src.memory.base import ExtractedFact

        db = MemoryDatabase(":memory:")
        await db.initialize()

        # 创建一个30天前的事实
        old_fact = ExtractedFact(
            fact_type="event",
            subject="旧事件",
            content="这是30天前的事",
            confidence=1.0,
        )
        old_fact.created_at = datetime.now() - timedelta(days=31)
        await db.save_fact(old_fact)

        # 创建一个今天的事实
        new_fact = ExtractedFact(
            fact_type="event",
            subject="新事件",
            content="这是今天的事",
            confidence=1.0,
        )
        await db.save_fact(new_fact)

        forgetter = Forgetter(db)
        count = await forgetter.forget_old_facts(days=30)

        assert count == 1

        # 验证旧事实被标记为inactive
        facts = await db.get_facts(limit=100)
        old_facts = [f for f in facts if f.subject == "旧事件"]
        new_facts = [f for f in facts if f.subject == "新事件"]

        assert len(old_facts) == 0  # inactive的不返回
        assert len(new_facts) == 1

        await db.close()

    @pytest.mark.asyncio
    async def test_deduplicate_facts(self):
        """重复事实被合并"""
        from src.memory.forgetter import Forgetter
        from src.memory.database import MemoryDatabase
        import uuid
        from datetime import datetime

        db = MemoryDatabase(":memory:")
        await db.initialize()

        # 直接用 SQL 插入重复记录（绕过 save_fact 的 upsert）
        now = datetime.now().isoformat()
        for i in range(3):
            await db._db.execute(
                """INSERT INTO facts
                   (id, fact_type, subject, content, confidence, source_message_id,
                    event_time, created_at, updated_at, is_active)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (str(uuid.uuid4()), "preference", "喜欢的食物", "喜欢吃火锅",
                 0.9, None, None, now, now, 1),
            )
        await db._db.commit()

        forgetter = Forgetter(db)
        count = await forgetter.deduplicate_facts()

        assert count >= 1

        await db.close()

    @pytest.mark.asyncio
    async def test_cleanup_low_confidence(self):
        """低置信度事实被清理"""
        from src.memory.forgetter import Forgetter
        from src.memory.database import MemoryDatabase
        from src.memory.base import ExtractedFact

        db = MemoryDatabase(":memory:")
        await db.initialize()

        # 创建低置信度事实
        low_fact = ExtractedFact(
            fact_type="opinion",
            subject="可能的观点",
            content="可能是这样",
            confidence=0.2,
        )
        await db.save_fact(low_fact)

        # 创建高置信度事实
        high_fact = ExtractedFact(
            fact_type="preference",
            subject="确定的偏好",
            content="确定喜欢",
            confidence=0.9,
        )
        await db.save_fact(high_fact)

        forgetter = Forgetter(db)
        count = await forgetter.cleanup_low_confidence(threshold=0.3)

        assert count == 1

        facts = await db.get_facts(limit=100)
        assert len(facts) == 1
        assert facts[0].subject == "确定的偏好"

        await db.close()

    @pytest.mark.asyncio
    async def test_run_all_cleanup(self):
        """执行所有清理任务"""
        from src.memory.forgetter import Forgetter
        from src.memory.database import MemoryDatabase

        db = MemoryDatabase(":memory:")
        await db.initialize()

        forgetter = Forgetter(db)
        result = await forgetter.run_all_cleanup()

        assert "forgotten" in result
        assert "deduplicated" in result
        assert "low_confidence" in result

        await db.close()
