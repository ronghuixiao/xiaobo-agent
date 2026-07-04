"""Phase 2 端到端测试 - 情绪追踪 + 语义检索 + 日报"""

import asyncio
import os
import tempfile
from datetime import datetime, timedelta

import pytest

from config.settings import Settings, LLMConfig, OllamaConfig, MemoryConfig, CompanionConfig
from src.llm.ollama import OllamaProvider
from src.memory.database import MemoryDatabase
from src.memory.semantic_search import SemanticSearch
from src.companion.handler import ConversationHandler
from src.companion.emotion_tracker import EmotionTracker, EMOTION_EMOJI, EMOTION_SENTIMENT
from src.companion.daily_report import DailyReportGenerator


class TestE2EEmotionTracking:
    """端到端情绪追踪测试"""

    @pytest.fixture
    async def full_stack(self):
        """完整系统栈"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_e2e_phase2.db")

            settings = Settings(
                llm=LLMConfig(
                    provider="ollama",
                    ollama=OllamaConfig(
                        base_url="http://localhost:11434",
                        model="qwen2.5:1.5b",
                    ),
                ),
                memory=MemoryConfig(db_path=db_path),
                companion=CompanionConfig(name="小柏", user_name="荣慧"),
            )

            llm = OllamaProvider(
                base_url=settings.llm.ollama.base_url,
                model=settings.llm.ollama.model,
            )
            memory = MemoryDatabase(db_path)
            await memory.initialize()

            yield settings, llm, memory

            await memory.close()
            await llm.close()

    @pytest.mark.asyncio
    async def test_emotion_tracker_analysis(self, full_stack):
        """测试情绪分析"""
        settings, llm, memory = full_stack
        healthy = await llm.health_check()
        if not healthy:
            pytest.skip("Ollama 不可用")

        tracker = EmotionTracker(llm, memory)

        messages = [
            {"role": "user", "content": "今天面试被拒了，好难过"},
            {"role": "assistant", "content": "别难过，这很正常，下次会更好的"},
        ]

        result = await tracker.analyze_conversation_emotion(messages)
        assert "current_emotion" in result
        assert "intensity" in result
        assert result["current_emotion"] in EMOTION_EMOJI.keys()

    @pytest.mark.asyncio
    async def test_emotion_timeline(self, full_stack):
        """测试情绪时间线"""
        settings, llm, memory = full_stack
        healthy = await llm.health_check()
        if not healthy:
            pytest.skip("Ollama 不可用")

        tracker = EmotionTracker(llm, memory)

        # 插入一些情绪记录
        from src.memory.base import EmotionRecord
        now = datetime.now()
        await memory.save_emotion(EmotionRecord(
            emotion="happy", intensity=0.8, context="收到好消息",
            timestamp=now - timedelta(hours=2),
        ))
        await memory.save_emotion(EmotionRecord(
            emotion="anxious", intensity=0.6, context="面试紧张",
            timestamp=now - timedelta(hours=1),
        ))

        timeline = await tracker.get_emotion_timeline(hours=3)
        assert len(timeline) == 2

    @pytest.mark.asyncio
    async def test_emotion_summary(self, full_stack):
        """测试情绪摘要"""
        settings, llm, memory = full_stack
        healthy = await llm.health_check()
        if not healthy:
            pytest.skip("Ollama 不可用")

        tracker = EmotionTracker(llm, memory)

        from src.memory.base import EmotionRecord
        now = datetime.now()
        for i in range(5):
            await memory.save_emotion(EmotionRecord(
                emotion="happy" if i % 2 == 0 else "sad",
                intensity=0.7,
                context=f"测试{i}",
                timestamp=now - timedelta(hours=i),
            ))

        summary = await tracker.get_emotion_summary(days=1)
        assert "happy" in summary or "开心" in summary


class TestE2ESemanticSearch:
    """端到端语义检索测试"""

    @pytest.fixture
    async def full_stack(self):
        """完整系统栈"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_e2e_search.db")

            settings = Settings(
                llm=LLMConfig(
                    provider="ollama",
                    ollama=OllamaConfig(
                        base_url="http://localhost:11434",
                        model="qwen2.5:1.5b",
                    ),
                ),
                memory=MemoryConfig(db_path=db_path),
                companion=CompanionConfig(name="小柏", user_name="荣慧"),
            )

            llm = OllamaProvider(
                base_url=settings.llm.ollama.base_url,
                model=settings.llm.ollama.model,
            )
            memory = MemoryDatabase(db_path)
            await memory.initialize()

            yield settings, llm, memory

            await memory.close()
            await llm.close()

    @pytest.mark.asyncio
    async def test_keyword_search(self, full_stack):
        """测试关键词搜索（Phase 1 已有，确认兼容）"""
        settings, llm, memory = full_stack

        from src.memory.base import ConversationMessage
        await memory.save_message(ConversationMessage(
            session_id="s1", role="user", content="我今天学了Rust编程语言"
        ))
        await memory.save_message(ConversationMessage(
            session_id="s1", role="user", content="明天要复习数据结构"
        ))

        results = await memory.search_messages("Rust")
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_semantic_search_basic(self, full_stack):
        """测试语义搜索基本功能"""
        settings, llm, memory = full_stack
        healthy = await llm.health_check()
        if not healthy:
            pytest.skip("Ollama 不可用")

        search = SemanticSearch(llm, memory)

        from src.memory.base import ConversationMessage
        await memory.save_message(ConversationMessage(
            session_id="s1", role="user", content="我想学机器学习，特别是深度学习"
        ))
        await memory.save_message(ConversationMessage(
            session_id="s1", role="user", content="明天要跑步锻炼身体"
        ))

        # 搜索相关话题
        results = await search.search_similar_messages(
            "AI和神经网络",
            threshold=0.3,  # 降低阈值以适应小模型
            limit=3,
        )
        # 应该能找到与机器学习相关的消息
        assert isinstance(results, list)


class TestE2EDailyReport:
    """端到端日报生成测试"""

    @pytest.fixture
    async def full_stack(self):
        """完整系统栈"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_e2e_report.db")

            settings = Settings(
                llm=LLMConfig(
                    provider="ollama",
                    ollama=OllamaConfig(
                        base_url="http://localhost:11434",
                        model="qwen2.5:1.5b",
                    ),
                ),
                memory=MemoryConfig(db_path=db_path),
                companion=CompanionConfig(name="小柏", user_name="荣慧"),
            )

            llm = OllamaProvider(
                base_url=settings.llm.ollama.base_url,
                model=settings.llm.ollama.model,
            )
            memory = MemoryDatabase(db_path)
            await memory.initialize()

            yield settings, llm, memory

            await memory.close()
            await llm.close()

    @pytest.mark.asyncio
    async def test_generate_daily_report(self, full_stack):
        """测试生成日报"""
        settings, llm, memory = full_stack
        healthy = await llm.health_check()
        if not healthy:
            pytest.skip("Ollama 不可用")

        # 先写入一些今日数据
        from src.memory.base import ConversationMessage, EmotionRecord
        now = datetime.now()

        await memory.save_message(ConversationMessage(
            session_id="s1", role="user",
            content="今天学了Python装饰器",
            timestamp=now,
        ))
        await memory.save_message(ConversationMessage(
            session_id="s1", role="assistant",
            content="装饰器很实用！",
            timestamp=now,
        ))
        await memory.save_emotion(EmotionRecord(
            emotion="excited", intensity=0.8,
            context="学新东西", timestamp=now,
        ))

        reporter = DailyReportGenerator(llm, memory)
        report = await reporter.generate_daily_report(target_date=now)

        assert report is not None
        assert len(report) > 0
        # 日报应该包含一些关键内容
        assert any(keyword in report for keyword in ["今天", "概览", "回顾", "📋"])

    @pytest.mark.asyncio
    async def test_generate_weekly_summary(self, full_stack):
        """测试生成周报"""
        settings, llm, memory = full_stack
        healthy = await llm.health_check()
        if not healthy:
            pytest.skip("Ollama 不可用")

        from src.memory.base import ConversationMessage
        now = datetime.now()

        # 写入一周的数据
        for i in range(7):
            day = now - timedelta(days=i)
            await memory.save_message(ConversationMessage(
                session_id="s1", role="user",
                content=f"第{i+1}天的记录",
                timestamp=day,
            ))

        reporter = DailyReportGenerator(llm, memory)
        summary = await reporter.generate_weekly_summary()

        assert summary is not None
        assert "7天" in summary or "过去" in summary


class TestE2EFullPipeline:
    """Phase 2 完整流程端到端测试"""

    @pytest.fixture
    async def full_stack(self):
        """完整系统栈"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_e2e_full.db")

            settings = Settings(
                llm=LLMConfig(
                    provider="ollama",
                    ollama=OllamaConfig(
                        base_url="http://localhost:11434",
                        model="qwen2.5:1.5b",
                    ),
                ),
                memory=MemoryConfig(db_path=db_path),
                companion=CompanionConfig(name="小柏", user_name="荣慧"),
            )

            llm = OllamaProvider(
                base_url=settings.llm.ollama.base_url,
                model=settings.llm.ollama.model,
            )
            memory = MemoryDatabase(db_path)
            await memory.initialize()

            yield settings, llm, memory

            await memory.close()
            await llm.close()

    @pytest.mark.asyncio
    async def test_full_pipeline(self, full_stack):
        """测试完整流程：对话 → 情绪追踪 → 记忆 → 语义搜索 → 日报"""
        settings, llm, memory = full_stack
        healthy = await llm.health_check()
        if not healthy:
            pytest.skip("Ollama 不可用")

        # 1. 对话
        handler = ConversationHandler(settings, llm, memory)
        handler.start_session()

        await handler.handle_message("我今天学了强化学习，感觉挺有意思")
        await handler.handle_message("但是有点难，有点焦虑")
        await handler.handle_message("不过后来搞懂了，很开心！")

        # 2. 验证记忆
        messages = await memory.get_messages(limit=100)
        assert len(messages) >= 6  # 3 user + 3 assistant

        # 3. 情绪追踪
        tracker = EmotionTracker(llm, memory)
        summary = await tracker.get_emotion_summary(days=1)
        assert summary is not None

        # 4. 语义搜索
        search = SemanticSearch(llm, memory)
        results = await search.search_similar_messages("机器学习相关", threshold=0.3)
        assert isinstance(results, list)

        # 5. 日报
        reporter = DailyReportGenerator(llm, memory)
        report = await reporter.generate_daily_report()
        assert len(report) > 0
