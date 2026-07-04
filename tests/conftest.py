"""测试共享 Fixtures"""

import asyncio
import os
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

# 设置测试环境变量
os.environ.setdefault("XIAOBO_TESTING", "1")

from config.settings import Settings, LLMConfig, OllamaConfig, MemoryConfig, CompanionConfig
from src.memory.database import MemoryDatabase
from src.memory.base import (
    ConversationMessage,
    ExtractedFact,
    EmotionRecord,
    AssociationIndex,
)


@pytest.fixture
def temp_db_path():
    """临时数据库路径"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield os.path.join(tmpdir, "test_memory.db")


@pytest.fixture
def test_settings(temp_db_path):
    """测试用配置"""
    return Settings(
        llm=LLMConfig(
            provider="ollama",
            ollama=OllamaConfig(
                base_url="http://localhost:11434",
                model="qwen2.5:1.5b",
                embedding_model="nomic-embed-text",
            ),
        ),
        memory=MemoryConfig(db_path=temp_db_path),
        companion=CompanionConfig(
            name="小柏",
            user_name="测试用户",
        ),
    )


@pytest_asyncio.fixture
async def memory_db(temp_db_path):
    """内存数据库 fixture"""
    db = MemoryDatabase(temp_db_path)
    await db.initialize()
    yield db
    await db.close()


@pytest.fixture
def sample_message():
    """样例对话消息"""
    return ConversationMessage(
        session_id="test-session-1",
        role="user",
        content="我今天学了强化学习，感觉挺有意思的",
    )


@pytest.fixture
def sample_messages():
    """样例对话消息列表"""
    return [
        ConversationMessage(
            session_id="test-session-1",
            role="user",
            content="我想学Rust，但不知道从哪开始",
        ),
        ConversationMessage(
            session_id="test-session-1",
            role="assistant",
            content="可以从 Rust Book 开始，每天看一章，配合练习。",
        ),
        ConversationMessage(
            session_id="test-session-1",
            role="user",
            content="好，我今天开始了，看了第一章",
        ),
        ConversationMessage(
            session_id="test-session-1",
            role="user",
            content="今天好累啊，面试被拒了",
        ),
    ]


@pytest.fixture
def sample_fact():
    """样例事实"""
    return ExtractedFact(
        fact_type="goal",
        subject="Rust学习",
        content="荣慧想学Rust，计划从Rust Book开始",
        confidence=0.9,
        source_message_id="msg-001",
    )


@pytest.fixture
def sample_emotion():
    """样例情绪记录"""
    return EmotionRecord(
        emotion="anxious",
        intensity=0.7,
        context="面试被拒",
        source_message_id="msg-004",
    )
