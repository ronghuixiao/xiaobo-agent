"""Ollama LLM Provider

连接本地 Docker 中运行的 Ollama 服务。
支持 chat completion 和 embedding。
"""

import logging
from typing import List, Optional

import httpx

from .base import ChatMessage, ChatResponse, LLMProvider

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    """Ollama 本地模型提供者"""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5:1.5b",
        embedding_model: str = "nomic-embed-text",
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.embedding_model = embedding_model
        self.default_temperature = temperature
        self.default_max_tokens = max_tokens
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=120.0)

    @property
    def name(self) -> str:
        return f"ollama:{self.model}"

    async def chat(
        self,
        messages: List[ChatMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> ChatResponse:
        """发送 chat completion 请求到 Ollama"""
        temp = temperature if temperature is not None else self.default_temperature
        tokens = max_tokens if max_tokens is not None else self.default_max_tokens

        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {
                "temperature": temp,
                "num_predict": tokens,
            },
        }

        try:
            resp = await self._client.post("/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()

            content = data.get("message", {}).get("content", "")
            return ChatResponse(
                content=content,
                model=self.model,
                usage={
                    "prompt_tokens": data.get("prompt_eval_count", 0),
                    "completion_tokens": data.get("eval_count", 0),
                },
                metadata={"total_duration": data.get("total_duration", 0)},
            )
        except httpx.HTTPError as e:
            logger.error(f"Ollama chat 请求失败: {e}")
            raise

    async def stream_chat(
        self,
        messages: List[ChatMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ):
        """流式 chat completion 请求到 Ollama"""
        temp = temperature if temperature is not None else self.default_temperature
        tokens = max_tokens if max_tokens is not None else self.default_max_tokens

        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
            "options": {
                "temperature": temp,
                "num_predict": tokens,
            },
        }

        try:
            async with self._client.stream("POST", "/api/chat", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line:
                        import json
                        data = json.loads(line)
                        if data.get("message", {}).get("content"):
                            yield data["message"]["content"]
        except httpx.HTTPError as e:
            logger.error(f"Ollama 流式请求失败: {e}")
            raise

    async def embed(self, text: str) -> List[float]:
        """获取文本的向量嵌入"""
        payload = {
            "model": self.embedding_model,
            "input": text,
        }

        try:
            resp = await self._client.post("/api/embed", json=payload)
            resp.raise_for_status()
            data = resp.json()
            embeddings = data.get("embeddings", [[]])
            return embeddings[0] if embeddings else []
        except httpx.HTTPError as e:
            logger.error(f"Ollama embed 请求失败: {e}")
            raise

    async def health_check(self) -> bool:
        """检查 Ollama 服务是否可用"""
        try:
            resp = await self._client.get("/api/tags")
            return resp.status_code == 200
        except Exception:
            return False

    async def close(self):
        """关闭 HTTP 客户端"""
        await self._client.aclose()
