"""信息抽取器单元测试"""

import json
import pytest
from unittest.mock import AsyncMock

from src.companion.extractor import MessageExtractor
from src.llm.base import ChatMessage, ChatResponse
from src.memory.base import ConversationMessage


class TestMessageExtractor:
    """MessageExtractor 测试"""

    @pytest.mark.asyncio
    async def test_extract_with_valid_json(self):
        """测试正常 JSON 抽取"""
        mock_llm = AsyncMock()
        llm_response = {
            "facts": [
                {"fact_type": "goal", "subject": "学习", "content": "想学Rust", "confidence": 0.9}
            ],
            "emotion": {"type": "excited", "intensity": 0.7, "context": "学新东西"},
            "topics": ["编程", "Rust"],
        }
        mock_llm.chat = AsyncMock(return_value=ChatResponse(
            content=json.dumps(llm_response, ensure_ascii=False)
        ))

        extractor = MessageExtractor(mock_llm)
        msg = ConversationMessage(
            session_id="s1",
            role="user",
            content="我想学Rust，感觉很兴奋！"
        )

        facts, emotion, topics = await extractor.extract(msg)
        assert len(facts) == 1
        assert facts[0].fact_type == "goal"
        assert emotion is not None
        assert emotion.emotion == "excited"
        assert "编程" in topics

    @pytest.mark.asyncio
    async def test_extract_with_empty_result(self):
        """测试无提取内容"""
        mock_llm = AsyncMock()
        llm_response = {
            "facts": [],
            "emotion": {"type": "neutral", "intensity": 0.5, "context": ""},
            "topics": [],
        }
        mock_llm.chat = AsyncMock(return_value=ChatResponse(
            content=json.dumps(llm_response, ensure_ascii=False)
        ))

        extractor = MessageExtractor(mock_llm)
        msg = ConversationMessage(
            session_id="s1",
            role="user",
            content="嗯"
        )

        facts, emotion, topics = await extractor.extract(msg)
        assert len(facts) == 0
        assert emotion is None  # neutral 不保存
        assert len(topics) == 0

    @pytest.mark.asyncio
    async def test_extract_with_invalid_json(self):
        """测试无效 JSON 的容错"""
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value=ChatResponse(
            content="这不是JSON"
        ))

        extractor = MessageExtractor(mock_llm)
        msg = ConversationMessage(
            session_id="s1",
            role="user",
            content="随便说点什么"
        )

        facts, emotion, topics = await extractor.extract(msg)
        assert len(facts) == 0
        assert emotion is None
        assert len(topics) == 0

    @pytest.mark.asyncio
    async def test_extract_handles_markdown_json(self):
        """测试处理 markdown 包裹的 JSON"""
        mock_llm = AsyncMock()
        llm_response = {
            "facts": [],
            "emotion": {"type": "happy", "intensity": 0.6, "context": "test"},
            "topics": ["日常"],
        }
        mock_llm.chat = AsyncMock(return_value=ChatResponse(
            content=f"```json\n{json.dumps(llm_response, ensure_ascii=False)}\n```"
        ))

        extractor = MessageExtractor(mock_llm)
        msg = ConversationMessage(
            session_id="s1",
            role="user",
            content="今天心情不错"
        )

        facts, emotion, topics = await extractor.extract(msg)
        assert emotion is not None
        assert emotion.emotion == "happy"
