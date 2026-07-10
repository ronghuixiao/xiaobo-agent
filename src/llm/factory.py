"""LLM Provider 工厂

根据配置自动创建对应的 LLM 提供者。
支持 Ollama 和 OpenAI 兼容 API。
聊天用配置的 provider，embedding 固定用 Ollama（因为云端 API 不一定支持）。
"""

from typing import Union

from config.settings import LLMConfig

from .base import LLMProvider
from .ollama import OllamaProvider
from .openai_provider import OpenAIProvider


def create_llm_provider(config: LLMConfig) -> Union[OllamaProvider, OpenAIProvider]:
    """根据配置创建 LLM 提供者"""
    if config.provider == "ollama":
        return OllamaProvider(
            base_url=config.ollama.base_url,
            model=config.ollama.model,
            embedding_model=config.ollama.embedding_model,
            temperature=config.ollama.temperature,
            max_tokens=config.ollama.max_tokens,
        )
    elif config.provider == "openai":
        return OpenAIProvider(
            api_key=config.openai.api_key,
            base_url=config.openai.base_url,
            model=config.openai.model,
            temperature=config.openai.temperature,
            max_tokens=config.openai.max_tokens,
        )
    else:
        raise ValueError(f"不支持的 LLM 提供者: {config.provider}")


def create_embedding_provider(config: LLMConfig) -> OllamaProvider:
    """创建 embedding 提供者（始终用 Ollama，云端 API 通常不支持 embedding）"""
    return OllamaProvider(
        base_url=config.ollama.base_url,
        model=config.ollama.model,
        embedding_model=config.ollama.embedding_model,
    )
