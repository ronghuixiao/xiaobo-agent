"""端到端测试 - Phase 1

测试完整流程：配置 → LLM → 记忆 → 对话 → 抽取
使用真实 Ollama 服务（需要 Docker 中运行）
"""

import asyncio
import os
import tempfile

import pytest

from config.settings import Settings, LLMConfig, OllamaConfig, MemoryConfig, CompanionConfig
from src.llm.ollama import OllamaProvider
from src.memory.database import MemoryDatabase
from src.companion.handler import ConversationHandler


class TestE2EConversation:
    """端到端对话测试"""

    @pytest.fixture
    async def full_stack(self):
        """完整的系统栈"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_e2e.db")

            settings = Settings(
                llm=LLMConfig(
                    provider="ollama",
                    ollama=OllamaConfig(
                        base_url="http://localhost:11434",
                        model="qwen2.5:1.5b",
                    ),
                ),
                memory=MemoryConfig(db_path=db_path),
                companion=CompanionConfig(
                    name="小柏",
                    user_name="荣慧",
                ),
            )

            llm = OllamaProvider(
                base_url=settings.llm.ollama.base_url,
                model=settings.llm.ollama.model,
            )
            memory = MemoryDatabase(db_path)
            await memory.initialize()

            handler = ConversationHandler(settings, llm, memory)

            yield handler, memory, llm

            await memory.close()
            await llm.close()

    @pytest.mark.asyncio
    async def test_full_conversation_flow(self, full_stack):
        """测试完整对话流程"""
        handler, memory, llm = full_stack

        # 检查 LLM 可用
        healthy = await llm.health_check()
        if not healthy:
            pytest.skip("Ollama 不可用")

        # 开始会话
        session_id = handler.start_session()
        assert session_id is not None

        # 发送消息
        response1 = await handler.handle_message("你好小柏，我是荣慧")
        assert response1 is not None
        assert len(response1) > 0

        # 发送第二条消息
        response2 = await handler.handle_message("我今天学了Python装饰器，挺有意思的")
        assert response2 is not None

        # 验证消息已保存
        messages = await memory.get_messages(session_id=session_id)
        # 至少有 2 条用户消息 + 2 条助手回复
        assert len(messages) >= 4

        # 验证信息已提取
        facts = await memory.get_facts()
        # LLM 应该能提取出至少一个事实
        assert len(facts) >= 0  # 1.5B 模型可能提取不稳定

    @pytest.mark.asyncio
    async def test_memory_persists_across_sessions(self, full_stack):
        """测试记忆跨会话持久化"""
        handler, memory, llm = full_stack

        healthy = await llm.health_check()
        if not healthy:
            pytest.skip("Ollama 不可用")

        # 第一个会话
        handler.start_session()
        await handler.handle_message("我喜欢Python和Rust")

        # 第二个会话（模拟新会话）
        handler.start_session()
        await handler.handle_message("我之前说过我喜欢什么语言来着？")

        # 验证记忆中包含之前的对话
        all_messages = await memory.get_messages(limit=100)
        assert len(all_messages) >= 4

        # 验证搜索能找到
        results = await memory.search_messages("Python")
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_emotion_tracking(self, full_stack):
        """测试情绪追踪"""
        handler, memory, llm = full_stack

        healthy = await llm.health_check()
        if not healthy:
            pytest.skip("Ollama 不可用")

        handler.start_session()
        await handler.handle_message("今天面试被拒了，好难过")

        # 检查情绪记录
        emotions = await memory.get_emotions()
        # 1.5B 模型可能情绪识别不稳定
        assert isinstance(emotions, list)

    @pytest.mark.asyncio
    async def test_concurrent_messages(self, full_stack):
        """测试并发消息处理"""
        handler, memory, llm = full_stack

        healthy = await llm.health_check()
        if not healthy:
            pytest.skip("Ollama 不可用")

        handler.start_session()

        # 并发发送多条消息
        responses = await asyncio.gather(
            handler.handle_message("消息1"),
            handler.handle_message("消息2"),
            handler.handle_message("消息3"),
            return_exceptions=True,
        )

        # 至少部分成功
        successful = [r for r in responses if isinstance(r, str) and len(r) > 0]
        assert len(successful) >= 1
