"""Step 1 测试：System Prompt 重构 - 学习伙伴角色"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestPromptRestructure:
    """测试 System Prompt 重构"""

    def test_prompt_has_learning_companion_section(self):
        """prompt 必须包含学习伙伴相关指令"""
        from src.companion.handler import SYSTEM_PROMPT_TEMPLATE
        # 必须有学习伙伴模式的定义
        assert "学习" in SYSTEM_PROMPT_TEMPLATE
        # 必须有追问/引导相关的指令
        assert any(kw in SYSTEM_PROMPT_TEMPLATE for kw in ["追问", "引导", "深入", "思考"])

    def test_prompt_allows_longer_responses_for_learning(self):
        """学习场景下允许更长、更有深度的回复"""
        from src.companion.handler import SYSTEM_PROMPT_TEMPLATE
        # prompt 应该说明学习内容可以回复更详细
        assert any(kw in SYSTEM_PROMPT_TEMPLATE for kw in ["学习内容", "详细", "深度", "扩展"])

    def test_prompt_has_mode_distinction(self):
        """prompt 必须区分闲聊模式和学习模式"""
        from src.companion.handler import SYSTEM_PROMPT_TEMPLATE
        # 必须有对话模式的区分
        assert any(kw in SYSTEM_PROMPT_TEMPLATE for kw in ["模式", "闲聊", "对话风格"])

    def test_prompt_still_has_anti_ai_rules(self):
        """重构后仍然保留反AI腔规则"""
        from src.companion.handler import SYSTEM_PROMPT_TEMPLATE
        assert "AI味" in SYSTEM_PROMPT_TEMPLATE or "AI腔" in SYSTEM_PROMPT_TEMPLATE
        assert "加油" in SYSTEM_PROMPT_TEMPLATE

    def test_prompt_has_learning_context_placeholder(self):
        """prompt 必须有学习记录的注入占位符"""
        from src.companion.handler import SYSTEM_PROMPT_TEMPLATE
        assert "{learning_context}" in SYSTEM_PROMPT_TEMPLATE

    def test_prompt_template_is_format_compatible(self):
        """prompt 模板必须能被 format 正确填充"""
        from src.companion.handler import SYSTEM_PROMPT_TEMPLATE
        # 所有占位符都能被填充
        test_filled = SYSTEM_PROMPT_TEMPLATE.format(
            companion_name="小柏",
            user_name="荣慧",
            current_date="2026年07月16日",
            current_time="21:00",
            known_facts="（测试）",
            recent_context="（测试）",
            related_memories="（测试）",
            today_tasks="（测试）",
            learning_context="（测试）",
        )
        assert "小柏" in test_filled
        assert "荣慧" in test_filled
        assert len(test_filled) > 100
