"""测试：LLM 驱动的任务识别"""

import pytest


class TestLLMTaskDetection:
    """测试 LLM 驱动的任务识别"""

    def test_prompt_has_task_extraction_instruction(self):
        """prompt 必须包含任务提取指令"""
        from src.companion.handler import SYSTEM_PROMPT_TEMPLATE
        assert "TASKS_DETECTED" in SYSTEM_PROMPT_TEMPLATE

    def test_prompt_no_date_in_task_detection(self):
        """prompt 任务提取不应要求 LLM 判断日期"""
        from src.companion.handler import SYSTEM_PROMPT_TEMPLATE
        # 任务提取部分不应该有日期相关指令
        assert "日期由系统根据消息时间自动处理" in SYSTEM_PROMPT_TEMPLATE

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
        assert tasks[0] == "中间件"

    def test_extract_tasks_no_tasks(self):
        """普通对话不提取任务"""
        from src.companion.handler import ConversationHandler
        response = "嗯嗯，今天学了反向传播，确实挺难的"
        tasks = ConversationHandler.extract_tasks_from_response(response)
        assert len(tasks) == 0

    def test_extract_tasks_returns_list_of_strings(self):
        """返回值是字符串列表"""
        from src.companion.handler import ConversationHandler
        response = "[TASKS_DETECTED]\n- A\n- B\n[/TASKS_DETECTED]"
        tasks = ConversationHandler.extract_tasks_from_response(response)
        assert isinstance(tasks, list)
        assert all(isinstance(t, str) for t in tasks)

    def test_extract_tasks_preserves_original_names(self):
        """保持用户原话"""
        from src.companion.handler import ConversationHandler
        response = "[TASKS_DETECTED]\n- Spring框架学习\n- hot100刷题\n[/TASKS_DETECTED]"
        tasks = ConversationHandler.extract_tasks_from_response(response)
        assert tasks[0] == "Spring框架学习"
        assert tasks[1] == "hot100刷题"
