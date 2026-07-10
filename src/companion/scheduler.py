"""定时任务调度器

管理定时任务：日报推送、情绪分析、清理过期数据等。
"""

import asyncio
import logging
from datetime import datetime, time, date
from typing import Callable, Coroutine, Optional

logger = logging.getLogger(__name__)


class CronScheduler:
    """轻量级定时任务调度器"""

    def __init__(self):
        self._tasks = []
        self._running = False
        self._last_run = {}  # name -> date, 防止同一天重复执行

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
        self._interval_last_run = {}  # name -> timestamp, 记录上次执行时间
        logger.info("调度器已启动")

        while self._running:
            now = datetime.now()
            now_ts = now.timestamp()

            for task in self._tasks:
                if task["type"] == "daily":
                    target = time(task["hour"], task["minute"])
                    now_time = now.time().replace(second=0, microsecond=0)

                    if now_time == target:
                        today = date.today()
                        last = self._last_run.get(task["name"])

                        if last == today:
                            continue

                        try:
                            logger.info(f"执行定时任务: {task['name']}")
                            await task["coro_factory"]()
                            self._last_run[task["name"]] = today
                            logger.info(f"定时任务 {task['name']} 执行完成")
                        except Exception as e:
                            logger.error(f"定时任务 {task['name']} 失败: {e}", exc_info=True)
                            self._last_run[task["name"]] = today

                elif task["type"] == "interval":
                    interval = task.get("interval", 3600)
                    last_ts = self._interval_last_run.get(task["name"], 0)
                    if now_ts - last_ts >= interval:
                        try:
                            logger.info(f"执行间隔任务: {task['name']}")
                            await task["coro_factory"]()
                            self._interval_last_run[task["name"]] = now_ts
                            logger.info(f"间隔任务 {task['name']} 执行完成")
                        except Exception as e:
                            logger.error(f"间隔任务 {task['name']} 失败: {e}", exc_info=True)
                            self._interval_last_run[task["name"]] = now_ts

            await asyncio.sleep(60)

    def stop(self):
        """停止调度器"""
        self._running = False
        logger.info("调度器已停止")
