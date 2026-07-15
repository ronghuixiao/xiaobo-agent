"""重试机制

提供异步重试装饰器和函数，支持指数退避。
用于 LLM 调用等可能因网络波动失败的操作。
"""

import asyncio
import logging
from typing import Any, Callable, Optional, Tuple, Type

logger = logging.getLogger(__name__)


async def retry_with_backoff(
    func: Callable,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
) -> Any:
    """异步重试函数，带指数退避

    Args:
        func: 要重试的异步函数
        max_retries: 最大重试次数
        base_delay: 基础延迟（秒）
        max_delay: 最大延迟（秒）
        retryable_exceptions: 可重试的异常类型

    Returns:
        函数返回值

    Raises:
        最后一次重试失败时的异常
    """
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            return await func()
        except retryable_exceptions as e:
            last_exception = e
            if attempt < max_retries:
                delay = min(base_delay * (2 ** attempt), max_delay)
                logger.warning(
                    f"重试 {attempt + 1}/{max_retries}，等待 {delay:.1f}s: {type(e).__name__}: {e}"
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    f"重试耗尽 ({max_retries}次): {type(e).__name__}: {e}"
                )

    raise last_exception


def retry_on_failure(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
):
    """重试装饰器

    用法：
        @retry_on_failure(max_retries=3)
        async def my_function():
            ...
    """
    def decorator(func: Callable):
        async def wrapper(*args, **kwargs):
            async def call():
                return await func(*args, **kwargs)
            return await retry_with_backoff(
                call,
                max_retries=max_retries,
                base_delay=base_delay,
                max_delay=max_delay,
                retryable_exceptions=retryable_exceptions,
            )
        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper
    return decorator
