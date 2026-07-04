"""记忆系统单元测试"""

import pytest
from datetime import datetime, timedelta

from src.memory.database import MemoryDatabase
from src.memory.base import (
    ConversationMessage,
    EmotionRecord,
    ExtractedFact,
    AssociationIndex,
)


class TestMemoryDatabase:
    """MemoryDatabase 基本操作测试"""

    @pytest.mark.asyncio
    async def test_save_and_get_message(self, memory_db):
        """测试保存和获取消息"""
        msg = ConversationMessage(
            session_id="s1",
            role="user",
            content="你好小柏",
        )
        msg_id = await memory_db.save_message(msg)
        assert msg_id is not None

        messages = await memory_db.get_messages(session_id="s1")
        assert len(messages) == 1
        assert messages[0].content == "你好小柏"
        assert messages[0].role == "user"

    @pytest.mark.asyncio
    async def test_messages_ordered_by_time(self, memory_db):
        """测试消息按时间排序"""
        for i in range(5):
            msg = ConversationMessage(
                session_id="s1",
                role="user",
                content=f"消息{i}",
                timestamp=datetime.now() + timedelta(seconds=i),
            )
            await memory_db.save_message(msg)

        messages = await memory_db.get_messages(session_id="s1")
        assert len(messages) == 5
        for i in range(4):
            assert messages[i].timestamp <= messages[i + 1].timestamp

    @pytest.mark.asyncio
    async def test_search_messages(self, memory_db):
        """测试消息搜索"""
        await memory_db.save_message(ConversationMessage(
            session_id="s1", role="user", content="今天学了Python装饰器"
        ))
        await memory_db.save_message(ConversationMessage(
            session_id="s1", role="user", content="明天要复习数据结构"
        ))
        await memory_db.save_message(ConversationMessage(
            session_id="s1", role="user", content="Python真的很有用"
        ))

        results = await memory_db.search_messages("Python")
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_save_and_get_fact(self, memory_db, sample_fact):
        """测试保存和获取事实"""
        fact_id = await memory_db.save_fact(sample_fact)
        assert fact_id is not None

        facts = await memory_db.get_facts(fact_type="goal")
        assert len(facts) == 1
        assert facts[0].subject == "Rust学习"

    @pytest.mark.asyncio
    async def test_search_facts(self, memory_db):
        """测试事实搜索"""
        await memory_db.save_fact(ExtractedFact(
            fact_type="preference",
            subject="编程语言",
            content="荣慧喜欢Python",
        ))
        await memory_db.save_fact(ExtractedFact(
            fact_type="ability",
            subject="技能",
            content="会用SQL和Git",
        ))

        results = await memory_db.search_facts("Python")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_save_and_get_emotion(self, memory_db, sample_emotion):
        """测试保存和获取情绪"""
        emotion_id = await memory_db.save_emotion(sample_emotion)
        assert emotion_id is not None

        emotions = await memory_db.get_emotions()
        assert len(emotions) == 1
        assert emotions[0].emotion == "anxious"

    @pytest.mark.asyncio
    async def test_emotions_filter_by_time(self, memory_db):
        """测试情绪按时间过滤"""
        now = datetime.now()
        await memory_db.save_emotion(EmotionRecord(
            emotion="happy", timestamp=now - timedelta(days=3)
        ))
        await memory_db.save_emotion(EmotionRecord(
            emotion="sad", timestamp=now - timedelta(days=1)
        ))

        recent = await memory_db.get_emotions(since=now - timedelta(days=2))
        assert len(recent) == 1
        assert recent[0].emotion == "sad"

    @pytest.mark.asyncio
    async def test_save_association_upsert(self, memory_db):
        """测试关联索引的 upsert"""
        assoc1 = AssociationIndex(
            keyword="Rust",
            message_ids=["msg1"],
            fact_ids=["fact1"],
        )
        await memory_db.save_association(assoc1)

        assoc2 = AssociationIndex(
            keyword="Rust",
            message_ids=["msg2"],
            fact_ids=["fact2"],
        )
        await memory_db.save_association(assoc2)

        results = await memory_db.get_associations("Rust")
        assert len(results) == 1
        assert len(results[0].message_ids) == 2
        assert "msg1" in results[0].message_ids
        assert "msg2" in results[0].message_ids

    @pytest.mark.asyncio
    async def test_stats(self, memory_db):
        """测试统计数据"""
        await memory_db.save_message(ConversationMessage(
            session_id="s1", role="user", content="测试"
        ))
        stats = await memory_db.get_stats()
        assert stats["conversations"] == 1
        assert stats["facts"] == 0
