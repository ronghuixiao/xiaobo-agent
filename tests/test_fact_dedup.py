"""测试 Fact 去重 + 衰减

1. save_fact 同 subject+fact_type 应该更新而不是插入
2. known_facts 分层过滤：稳定画像全保留，事件/承诺只保留近期
"""
import pytest
from datetime import datetime, timedelta
from src.memory.database import MemoryDatabase, ExtractedFact


def _make_fact(subject="实验", content="实验完成", fact_type="event",
               event_time=None, created_at=None):
    now = datetime.now()
    return ExtractedFact(
        id=f"fact-{subject}-{hash(content) & 0xFFFFFF:06x}",
        fact_type=fact_type,
        subject=subject,
        content=content,
        confidence=0.9,
        source_message_id=None,
        event_time=event_time,
        created_at=created_at or now,
        updated_at=now,
        is_active=True,
    )


class TestFactUpsert:
    """测试 upsert 去重"""

    @pytest.mark.asyncio
    async def test_same_subject_updates_not_inserts(self, tmp_path):
        """同一 subject+fact_type 的事实应该更新而不是插入"""
        db = MemoryDatabase(str(tmp_path / "test.db"))
        await db.initialize()

        # 第一次插入
        fact1 = _make_fact(subject="实验", content="实验完成")
        await db.save_fact(fact1)

        # 第二次：同 subject+fact_type，不同 content
        fact2 = _make_fact(subject="实验", content="实验做完了")
        await db.save_fact(fact2)

        facts = await db.get_facts()
        # 应该只有1条，不是2条
        assert len(facts) == 1
        assert facts[0].content == "实验做完了"

    @pytest.mark.asyncio
    async def test_different_subject_still_inserts(self, tmp_path):
        """不同 subject 的事实正常插入"""
        db = MemoryDatabase(str(tmp_path / "test.db"))
        await db.initialize()

        await db.save_fact(_make_fact(subject="实验", content="实验完成"))
        await db.save_fact(_make_fact(subject="hot100", content="完成hot100"))

        facts = await db.get_facts()
        assert len(facts) == 2

    @pytest.mark.asyncio
    async def test_different_fact_type_still_inserts(self, tmp_path):
        """同 subject 但不同 fact_type 的事实正常插入"""
        db = MemoryDatabase(str(tmp_path / "test.db"))
        await db.initialize()

        await db.save_fact(_make_fact(subject="实验", content="实验完成", fact_type="event"))
        await db.save_fact(_make_fact(subject="实验", content="实验要做", fact_type="commitment"))

        facts = await db.get_facts()
        assert len(facts) == 2


class TestKnownFactsFiltering:
    """测试 known_facts 分层过滤"""

    @pytest.mark.asyncio
    async def test_preference_and_opinion_all_kept(self, tmp_path):
        """偏好和观点类事实全部保留"""
        db = MemoryDatabase(str(tmp_path / "test.db"))
        await db.initialize()

        # 插入30天前的偏好
        old = datetime.now() - timedelta(days=30)
        await db.save_fact(_make_fact(subject="汽水", content="喜欢荔枝味汽水",
                                       fact_type="preference", created_at=old))
        await db.save_fact(_make_fact(subject="学习", content="觉得TDD有意思",
                                       fact_type="opinion", created_at=old))
        await db.save_fact(_make_fact(subject="饮食", content="喜欢吃辣",
                                       fact_type="preference", created_at=old))

        # 调用分层过滤
        facts = await db.get_facts(limit=100)

        # 稳定画像类全部保留
        stable = [f for f in facts if f.fact_type in ("preference", "opinion", "habit", "person", "goal")]
        assert len(stable) == 3

    @pytest.mark.asyncio
    async def test_old_events_filtered(self, tmp_path):
        """7天前的事件只保留每个 subject 最新的1条"""
        db = MemoryDatabase(str(tmp_path / "test.db"))
        await db.initialize()

        # 7天前的"实验完成"
        old = datetime.now() - timedelta(days=8)
        await db.save_fact(_make_fact(subject="实验", content="实验完成",
                                       fact_type="event", created_at=old))

        # 今天的"实验做完"
        today = datetime.now() - timedelta(hours=1)
        await db.save_fact(_make_fact(subject="实验", content="实验做完",
                                       fact_type="event", created_at=today))

        facts = await db.get_facts(limit=100)
        # 同 subject 的 event 应该只保留最新1条
        events = [f for f in facts if f.fact_type == "event" and f.subject == "实验"]
        assert len(events) == 1
        assert events[0].content == "实验做完"
