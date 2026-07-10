"""LLM Provider 抽象基类

所有 LLM 提供者必须实现这个接口。
支持 chat completion、streaming chat 和 embedding 三种能力。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, AsyncGenerator


@dataclass
class ChatMessage:
    """对话消息"""
    role: str  # "system", "user", "assistant"
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatResponse:
    """对话响应"""
    content: str
    model: str = ""
    usage: Dict[str, int] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class LLMProvider(ABC):
    """LLM 提供者抽象基类"""

    @abstractmethod
    async def chat(
        self,
        messages: List[ChatMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> ChatResponse:
        """发送对话请求"""
        ...

    @abstractmethod
    async def stream_chat(
        self,
        messages: List[ChatMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """流式对话请求，逐token返回"""
        ...
        yield  # Make it a generator

    @abstractmethod
    async def embed(self, text: str) -> List[float]:
        """获取文本的向量嵌入"""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """检查服务是否可用"""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """提供者名称"""
        ...
