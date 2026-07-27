"""LLM 容错层 — 兜底 + 熔断 + 缓存

三层防护：
1. 兜底（Fallback）: LLM失败时返回友好提示，不让用户无限等待
2. 熔断（Circuit Breaker）: 连续失败N次后停止调用，避免雪崩，冷却后自动恢复
3. 缓存（Cache）: 相同query返回缓存结果，减少LLM调用次数

使用方式：
    resilience = LLMResilience(llm)
    response = await resilience.chat(messages, temperature=0.7)
"""
import time
import hashlib
import json
import logging
from typing import Dict, List, Optional
from enum import Enum

from src.llm.base import LLMProvider, ChatMessage, ChatResponse

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """熔断器状态"""
    CLOSED = "closed"      # 正常：允许调用
    OPEN = "open"          # 熔断：拒绝调用
    HALF_OPEN = "half_open"  # 半开：允许少量试探调用


class CircuitBreaker:
    """熔断器 — 连续失败后停止调用，避免雪崩
    
    状态机：
    CLOSED（正常）→ 连续失败N次 → OPEN（熔断）→ 冷却时间到 → HALF_OPEN（试探）
    → 试探成功 → CLOSED（恢复）
    → 试探失败 → OPEN（继续熔断）
    """
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        """
        Args:
            failure_threshold: 连续失败多少次触发熔断
            recovery_timeout: 熔断后多少秒进入半开状态（秒）
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
    
    def record_success(self):
        """记录成功调用"""
        self.failure_count = 0
        if self.state != CircuitState.CLOSED:
            logger.info("🔌 熔断器恢复: HALF_OPEN → CLOSED")
        self.state = CircuitState.CLOSED
    
    def record_failure(self):
        """记录失败调用"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            if self.state != CircuitState.OPEN:
                logger.warning(f"🔌 熔断器触发: 连续{self.failure_count}次失败 → OPEN")
            self.state = CircuitState.OPEN
    
    def can_execute(self) -> bool:
        """检查是否允许调用"""
        if self.state == CircuitState.CLOSED:
            return True
        
        if self.state == CircuitState.OPEN:
            # 检查冷却时间是否已过
            elapsed = time.time() - self.last_failure_time
            if elapsed >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                logger.info("🔌 熔断器进入半开状态: OPEN → HALF_OPEN")
                return True
            return False
        
        if self.state == CircuitState.HALF_OPEN:
            return True  # 允许一次试探调用
        
        return False
    
    def get_status(self) -> Dict:
        """获取熔断器状态"""
        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
        }


class ResponseCache:
    """LLM 响应缓存 — 相同query返回缓存结果
    
    使用 LRU + TTL 策略：
    - 最多缓存 max_size 条
    - 超过 ttl 秒的缓存自动失效
    - 相同 messages 内容返回缓存
    """
    
    def __init__(self, max_size: int = 100, ttl: int = 3600):
        """
        Args:
            max_size: 最大缓存条数
            ttl: 缓存有效期（秒），默认1小时
        """
        self.max_size = max_size
        self.ttl = ttl
        self._cache: Dict[str, Dict] = {}  # key -> {"response": ..., "timestamp": ...}
    
    def _make_key(self, messages: List[ChatMessage], temperature: float) -> str:
        """生成缓存key"""
        content = json.dumps([
            {"role": m.role, "content": m.content[:200]}  # 截取前200字符避免key过长
            for m in messages
        ], ensure_ascii=False)
        raw = f"{content}|{temperature}"
        return hashlib.md5(raw.encode()).hexdigest()
    
    def get(self, messages: List[ChatMessage], temperature: float) -> Optional[str]:
        """获取缓存"""
        key = self._make_key(messages, temperature)
        if key in self._cache:
            entry = self._cache[key]
            if time.time() - entry["timestamp"] < self.ttl:
                logger.info(f"📦 缓存命中: {key[:8]}...")
                return entry["response"]
            else:
                del self._cache[key]  # 过期删除
        return None
    
    def set(self, messages: List[ChatMessage], temperature: float, response: str):
        """写入缓存"""
        key = self._make_key(messages, temperature)
        
        # LRU: 如果满了，删最旧的
        if len(self._cache) >= self.max_size:
            oldest_key = min(self._cache, key=lambda k: self._cache[k]["timestamp"])
            del self._cache[oldest_key]
        
        self._cache[key] = {
            "response": response,
            "timestamp": time.time(),
        }
    
    def clear(self):
        """清空缓存"""
        self._cache.clear()
    
    def get_stats(self) -> Dict:
        """获取缓存统计"""
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "ttl": self.ttl,
        }


class LLMResilience:
    """LLM 容错层 — 整合兜底 + 熔断 + 缓存
    
    调用链：
    1. 检查熔断器 → 如果OPEN，直接返回兜底提示
    2. 检查缓存 → 如果命中，直接返回缓存
    3. 调用LLM → 成功则记录成功+写缓存
    4. 调用LLM → 失败则记录失败+返回兜底提示
    """
    
    # 兜底提示
    FALLBACK_MESSAGES = [
        "我现在有点累，稍后再聊吧 😴",
        "网络好像不太稳定，等一下再说？",
        "抱歉，我暂时无法回复，请稍后再试。",
    ]
    
    def __init__(
        self,
        llm: LLMProvider,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        cache_size: int = 100,
        cache_ttl: int = 3600,
    ):
        self.llm = llm
        self.breaker = CircuitBreaker(failure_threshold, recovery_timeout)
        self.cache = ResponseCache(cache_size, cache_ttl)
        self._fallback_index = 0
    
    def _get_fallback(self) -> str:
        """获取轮询的兜底提示"""
        msg = self.FALLBACK_MESSAGES[self._fallback_index % len(self.FALLBACK_MESSAGES)]
        self._fallback_index += 1
        return msg
    
    async def chat(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> ChatResponse:
        """带容错的LLM调用"""
        
        # 1. 熔断器检查
        if not self.breaker.can_execute():
            logger.warning("🔌 熔断中，返回兜底提示")
            return ChatResponse(content=self._get_fallback())
        
        # 2. 缓存检查（只缓存非流式调用）
        cached = self.cache.get(messages, temperature)
        if cached:
            return ChatResponse(content=cached)
        
        # 3. 调用LLM
        try:
            response = await self.llm.chat(messages, temperature=temperature, max_tokens=max_tokens)
            self.breaker.record_success()
            self.cache.set(messages, temperature, response.content)
            return response
        except Exception as e:
            logger.error(f"LLM调用失败: {e}")
            self.breaker.record_failure()
            return ChatResponse(content=self._get_fallback())
    
    async def stream_chat(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ):
        """带容错的流式LLM调用"""
        
        # 1. 熔断器检查
        if not self.breaker.can_execute():
            logger.warning("🔌 熔断中，返回兜底提示")
            yield self._get_fallback()
            return
        
        # 2. 流式调用（不走缓存）
        try:
            async for chunk in self.llm.stream_chat(messages, temperature=temperature, max_tokens=max_tokens):
                yield chunk
            self.breaker.record_success()
        except Exception as e:
            logger.error(f"LLM流式调用失败: {e}")
            self.breaker.record_failure()
            yield self._get_fallback()
    
    async def embed(self, text: str) -> List[float]:
        """带容错的embedding调用"""
        if not self.breaker.can_execute():
            logger.warning("🔌 熔断中，embedding返回零向量")
            return [0.0] * 384  # nomic-embed-text 维度
        
        try:
            result = await self.llm.embed(text)
            self.breaker.record_success()
            return result
        except Exception as e:
            logger.error(f"Embedding调用失败: {e}")
            self.breaker.record_failure()
            return [0.0] * 384
    
    def get_status(self) -> Dict:
        """获取容错层状态"""
        return {
            "breaker": self.breaker.get_status(),
            "cache": self.cache.get_stats(),
        }
