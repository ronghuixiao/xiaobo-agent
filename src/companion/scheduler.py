"""定时任务调度器

管理定时任务：日报推送、情绪分析、清理过期数据等。
"""

import asyncio
import logging
from datetime import datetime, time
from typing import Callable, Coroutine, Optional

logger = logging.getLogger(__name__)


class CronScheduler:
    """轻量级定时任务调度器"""

    def __init__(self):
        self._tasks = []
        self._running = False

    def schedule_daily(
        self,
        name: str,
        hour: int,
        minute: int,
        coro_factory: Callable[[], Coroutine],
    ):
        """注册每日定时任务"""
        self._tasks.append({
            "name": name,
            "hour": hour,
            "minute": minute,
            "coro_factory": coro_factory,
            "type": "daily",
        })
        logger.info(f"注册定时任务: {name} @ {hour:02d}:{minute:02d}")

    def schedule_interval(
        self,
        name: str,
        interval_seconds: int,
        coro_factory: Callable[[], Coroutine],
    ):
        """注册间隔定时任务"""
        self._tasks.append({
            "name": name,
            "interval": interval_seconds,
            "coro_factory": coro_factory,
            "type": "interval",
        })
        logger.info(f"注册间隔任务: {name} (每{interval_seconds}秒)")

    async def start(self):
        """启动调度器"""
        self._running = True
        logger.info("调度器已启动")

        while self._running:
            now = datetime.now()

            for task in self._tasks:
                if task["type"] == "daily":
                    target = time(task["hour"], task["minute"])
                    if now.time().replace(second=0, microsecond=0) == target:
                        try:
                            logger.info(f"执行定时任务: {task['name']}")
                            await task["coro_factory"]()
                        except Exception as e:
                            logger.error(f"定时任务 {task['name']} 失败: {e}")

            # 每30秒检查一次
            await asyncio.sleep(30)

    def stop(self):
        """停止调度器"""
        self._running = False
        logger.info("调度器已停止")
