"""语义搜索集成测试"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime


class TestSemanticSearchIntegration:
    """测试语义搜索集成到 handler"""

    def test_semantic_search_class_exists(self):
        """语义搜索类存在"""
        from src.memory.semantic_search import SemanticSearch
        assert hasattr(SemanticSearch, 'search_similar_messages')
        assert hasattr(SemanticSearch, 'find_related_facts')

    def test_handler_has_related_method(self):
        """handler 有获取相关记忆的方法"""
        from src.companion.handler import ConversationHandler
        assert hasattr(ConversationHandler, '_get_related_memories')

    @pytest.mark.asyncio
    async def test_get_related_memories_returns_string(self):
        """_get_related_memories 返回格式化字符串"""
        from src.companion.handler import ConversationHandler
        from config.settings import Settings

        mock_llm = AsyncMock()
        mock_memory = AsyncMock()
        mock_memory.get_messages = AsyncMock(return_value=[])
        mock_memory.get_facts = AsyncMock(return_value=[])

        settings = Settings()
        handler = ConversationHandler(settings, mock_llm, mock_memory)

        result = await handler._get_related_memories("测试查询")
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_get_related_memories_with_no_data(self):
        """无数据时返回暂无相关记忆"""
        from src.companion.handler import ConversationHandler
        from config.settings import Settings

        mock_llm = AsyncMock()
        mock_llm.embed = AsyncMock(return_value=[0.1] * 384)
        mock_memory = AsyncMock()
        mock_memory.get_messages = AsyncMock(return_value=[])
        mock_memory.get_facts = AsyncMock(return_value=[])

        settings = Settings()
        handler = ConversationHandler(settings, mock_llm, mock_memory)

        result = await handler._get_related_memories("测试查询")
        # 无数据时应该返回空或暂无相关记忆
        assert result == "" or "暂无" in result or len(result) < 20

    def test_system_prompt_has_related_memories(self):
        """系统提示模板包含相关记忆占位符"""
        from src.companion.handler import SYSTEM_PROMPT_TEMPLATE
        assert "{related_memories}" in SYSTEM_PROMPT_TEMPLATE
