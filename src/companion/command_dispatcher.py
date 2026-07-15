"""命令分发器

统一处理来自不同通道（微信、飞书、交互模式）的命令。
消除各通道重复的命令分发逻辑。
"""

import logging
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class CommandDispatcher:
    """命令分发器

    将消息路由到对应的处理器：
    - 日报/周报/月报/情绪/模式/统计 → 专用处理器
    - 其他消息 → 对话流程（含任务检测）
    """

    KNOWN_COMMANDS = {"日报", "周报", "月报", "情绪", "模式", "统计"}

    def __init__(
        self,
        daily_report=None,
        report_gen=None,
        tracker=None,
        analyzer=None,
        memory=None,
        handler=None,
        task_mgr=None,
        llm=None,
    ):
        self.daily_report = daily_report
        self.report_gen = report_gen
        self.tracker = tracker
        self.analyzer = analyzer
        self.memory = memory
        self.handler = handler
        self.task_mgr = task_mgr
        self.llm = llm

    def is_known_command(self, text: str) -> bool:
        """判断是否为已知命令"""
        return text.strip() in self.KNOWN_COMMANDS

    async def dispatch(self, message: str) -> str:
        """分发消息，返回回复文本

        已知命令直接返回格式化文本。
        未知消息走对话流程（含任务检测）。
        """
        content = message.strip()

        # === 已知命令 ===
        if content == "日报":
            report = await self.daily_report.generate_daily_report()
            return f"📋 今日日报\n\n{report}"

        if content == "周报":
            report = await self.report_gen.generate_weekly_report()
            return f"📋 周报\n\n{report}"

        if content == "月报":
            report = await self.report_gen.generate_monthly_report()
            return f"📋 月报\n\n{report}"

        if content == "情绪":
            summary = await self.tracker.get_emotion_summary(days=7)
            return f"🎭 情绪摘要\n\n{summary}"

        if content == "模式":
            pattern = await self.analyzer.analyze_weekly_pattern()
            return (
                f"📊 本周模式\n"
                f"总消息: {pattern['total_messages']}\n"
                f"最忙: {pattern['busiest_day']}\n"
                f"最闲: {pattern['quietest_day']}"
            )

        if content == "统计":
            stats = await self.memory.get_stats()
            return f"📊 记忆统计: {stats}"

        # === 未知消息 → 对话流程 ===
        # 1. 检测任务列表
        if self.task_mgr:
            self.task_mgr.detect_task_list(content)

        # 2. 调用对话处理器
        response = await self.handler.handle_message(content)

        # 3. 检测任务完成
        if self.task_mgr and self.llm:
            self.task_mgr.detect_task_completion(content, self.llm)
            self.task_mgr.detect_task_completion(response, self.llm)

        return response
