"""LLM Provider 单元测试"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.llm.base import ChatMessage, ChatResponse, LLMProvider
from src.llm.ollama import OllamaProvider
from src.llm.openai_provider import OpenAIProvider
from src.llm.factory import create_llm_provider
from config.settings import LLMConfig, OllamaConfig, OpenAIConfig


class TestOllamaProvider:
    """Ollama Provider 测试"""

    def test_init(self):
        """测试初始化"""
        provider = OllamaProvider(
            base_url="http://localhost:11434",
            model="qwen2.5:1.5b",
        )
        assert provider.name == "ollama:qwen2.5:1.5b"
        assert provider.base_url == "http://localhost:11434"

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """测试健康检查（需要 Ollama 运行）"""
        provider = OllamaProvider(base_url="http://localhost:11434")
        result = await provider.health_check()
        assert isinstance(result, bool)
        await provider.close()

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        """测试健康检查失败（端口不存在）"""
        provider = OllamaProvider(base_url="http://localhost:99999")
        result = await provider.health_check()
        assert result is False
        await provider.close()


class TestOpenAIProvider:
    """OpenAI Provider 测试"""

    def test_init(self):
        """测试初始化"""
        provider = OpenAIProvider(
            api_key="test-key",
            base_url="https://api.openai.com/v1",
            model="gpt-4o-mini",
        )
        assert provider.name == "openai:gpt-4o-mini"

    def test_init_custom_base_url(self):
        """测试自定义 base_url（Mimo 等）"""
        provider = OpenAIProvider(
            api_key="test-key",
            base_url="https://mimo.example.com/v1",
            model="mimo-v2.5",
        )
        assert provider.name == "openai:mimo-v2.5"


class TestLLMFactory:
    """LLM 工厂测试"""

    def test_create_ollama(self):
        """测试创建 Ollama 提供者"""
        config = LLMConfig(
            provider="ollama",
            ollama=OllamaConfig(model="qwen2.5:1.5b"),
        )
        provider = create_llm_provider(config)
        assert isinstance(provider, OllamaProvider)

    def test_create_openai(self):
        """测试创建 OpenAI 提供者"""
        config = LLMConfig(
            provider="openai",
            openai=OpenAIConfig(api_key="test", model="gpt-4o-mini"),
        )
        provider = create_llm_provider(config)
        assert isinstance(provider, OpenAIProvider)

    def test_create_unknown_raises(self):
        """测试未知提供者抛异常"""
        config = LLMConfig(provider="unknown")
        with pytest.raises(ValueError, match="不支持"):
            create_llm_provider(config)
