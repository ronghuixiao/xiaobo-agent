"""OpenAI 兼容 LLM Provider

支持 OpenAI、Mimo 等所有 OpenAI 兼容 API。
使用 openai 官方 SDK。
"""

import logging
from typing import AsyncGenerator, List, Optional

from openai import AsyncOpenAI

from .base import ChatMessage, ChatResponse, LLMProvider

logger = logging.getLogger(__name__)


class OpenAIProvider(LLMProvider):
    """OpenAI 兼容 API 提供者"""

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ):
        self.model = model
        self.default_temperature = temperature
        self.default_max_tokens = max_tokens
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    @property
    def name(self) -> str:
        return f"openai:{self.model}"

    async def chat(
        self,
        messages: List[ChatMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> ChatResponse:
        """发送 chat completion 请求（带重试）"""
        from src.llm.retry import retry_with_backoff

        async def _do_chat():
            temp = temperature if temperature is not None else self.default_temperature
            tokens = max_tokens if max_tokens is not None else self.default_max_tokens

            response = await self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": m.role, "content": m.content} for m in messages],
                temperature=temp,
                max_tokens=tokens,
            )

            choice = response.choices[0]
            return ChatResponse(
                content=choice.message.content or "",
                model=response.model,
                usage={
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                },
            )

        try:
            return await retry_with_backoff(
                _do_chat,
                max_retries=3,
                base_delay=1.0,
                max_delay=10.0,
            )
        except Exception as e:
            logger.error(f"OpenAI API 请求失败（重试耗尽）: {e}")
            raise

    async def stream_chat(
        self,
        messages: List[ChatMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """流式 chat completion 请求，逐token返回"""
        temp = temperature if temperature is not None else self.default_temperature
        tokens = max_tokens if max_tokens is not None else self.default_max_tokens

        try:
            stream = await self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": m.role, "content": m.content} for m in messages],
                temperature=temp,
                max_tokens=tokens,
                stream=True,
            )
            
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.error(f"OpenAI 流式请求失败: {e}")
            raise

    async def embed(self, text: str) -> List[float]:
        """获取文本的向量嵌入"""
        try:
            response = await self._client.embeddings.create(
                model="text-embedding-3-small",
                input=text,
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"OpenAI embed 请求失败: {e}")
            raise

    async def health_check(self) -> bool:
        """检查 API 是否可用"""
        try:
            await self._client.models.list()
            return True
        except Exception:
            return False

    async def close(self):
        """关闭客户端"""
        await self._client.close()
