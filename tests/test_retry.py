"""LLM 重试机制测试"""

import pytest
from unittest.mock import AsyncMock, MagicMock
import asyncio


class TestLLMRetry:
    """LLM 调用重试测试"""

    @pytest.mark.asyncio
    async def test_retry_succeeds_after_failures(self):
        """前几次失败后成功"""
        from src.llm.retry import retry_with_backoff

        call_count = 0

        async def flaky_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("连接失败")
            return "成功"

        result = await retry_with_backoff(flaky_operation, max_retries=3, base_delay=0.01)
        assert result == "成功"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_exhausted_raises(self):
        """超过重试次数后抛出异常"""
        from src.llm.retry import retry_with_backoff

        async def always_fail():
            raise ConnectionError("始终失败")

        with pytest.raises(ConnectionError, match="始终失败"):
            await retry_with_backoff(always_fail, max_retries=2, base_delay=0.01)

    @pytest.mark.asyncio
    async def test_no_retry_on_success(self):
        """成功时不重试"""
        from src.llm.retry import retry_with_backoff

        call_count = 0

        async def success():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await retry_with_backoff(success, max_retries=3, base_delay=0.01)
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_respects_exceptions(self):
        """只重试指定异常类型"""
        from src.llm.retry import retry_with_backoff

        call_count = 0

        async def type_error():
            nonlocal call_count
            call_count += 1
            raise TypeError("类型错误")

        with pytest.raises(TypeError):
            await retry_with_backoff(
                type_error,
                max_retries=3,
                base_delay=0.01,
                retryable_exceptions=(ConnectionError,),
            )
        assert call_count == 1  # 没有重试

    @pytest.mark.asyncio
    async def test_exponential_backoff_delays(self):
        """重试间隔指数增长"""
        from src.llm.retry import retry_with_backoff
        import time

        call_count = 0

        async def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 4:
                raise ConnectionError("失败")
            return "ok"

        start = time.monotonic()
        result = await retry_with_backoff(
            fail_then_succeed,
            max_retries=5,
            base_delay=0.05,
            max_delay=1.0,
        )
        elapsed = time.monotonic() - start
        assert result == "ok"
        assert elapsed >= 0.1  # 至少等了两次重试的延迟
