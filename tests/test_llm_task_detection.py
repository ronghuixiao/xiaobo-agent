"""测试：LLM 驱动的任务识别"""

import pytest


class TestLLMTaskDetection:
    """测试 LLM 驱动的任务识别"""

    def test_prompt_has_task_extraction_instruction(self):
        """prompt 必须包含任务提取指令"""
        from src.companion.handler import SYSTEM_PROMPT_TEMPLATE
        # 必须有任务提取的结构化输出指令
        assert "TASKS_DETECTED" in SYSTEM_PROMPT_TEMPLATE or "tasks_detected" in SYSTEM_PROMPT_TEMPLATE

    def test_prompt_mentions_date_inference(self):
        """prompt 必须提到日期推断能力"""
        from src.companion.handler import SYSTEM_PROMPT_TEMPLATE
        assert any(kw in SYSTEM_PROMPT_TEMPLATE for kw in ["日期", "明天", "推断"])

    def test_extract_tasks_from_response_basic(self):
        """从 LLM 回复中提取任务"""
        from src.companion.handler import ConversationHandler
        response = """好的，我记下了。

[TASKS_DETECTED]
- 中间件
- 数据结构与算法
- hot100
- 实验
- 锻炼
[/TASKS_DETECTED]"""
        tasks = ConversationHandler.extract_tasks_from_response(response)
        assert len(tasks) == 5
        assert tasks[0]["title"] == "中间件"

    def test_extract_tasks_with_date(self):
        """提取带日期的任务"""
        from src.companion.handler import ConversationHandler
        response = """好的。

[TASKS_DETECTED: 2026-07-18]
- 中间件
- 数据结构
[/TASKS_DETECTED]"""
        tasks = ConversationHandler.extract_tasks_from_response(response)
        assert len(tasks) == 2
        assert tasks[0]["date"] == "2026-07-18"

    def test_extract_tasks_no_tasks(self):
        """普通对话不提取任务"""
        from src.companion.handler import ConversationHandler
        response = "嗯嗯，今天学了反向传播，确实挺难的"
        tasks = ConversationHandler.extract_tasks_from_response(response)
        assert len(tasks) == 0

    def test_extract_tasks_from_various_formats(self):
        """各种任务格式"""
        from src.companion.handler import ConversationHandler
        # 无日期
        r1 = "[TASKS_DETECTED]\n- A\n- B\n[/TASKS_DETECTED]"
        assert len(ConversationHandler.extract_tasks_from_response(r1)) == 2

        # 有日期
        r2 = "[TASKS_DETECTED: 明天]\n- C\n[/TASKS_DETECTED]"
        tasks = ConversationHandler.extract_tasks_from_response(r2)
        assert len(tasks) == 1
        # 明天应该被解析为具体日期
        assert tasks[0]["date"] != ""
