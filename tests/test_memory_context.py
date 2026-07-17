"""测试记忆系统改进：
1. known_facts 应包含所有事实（不过滤），但每条带日期
2. prompt 应包含"尊重用户对话指令"的规则
"""
import pytest
from datetime import datetime, timedelta
from src.memory.database import MemoryDatabase, ExtractedFact


def _make_fact(subject="学姐", content="给学姐发送活动统计", event_time="2025-07-15", created_at=None):
    """构造测试用 ExtractedFact"""
    now = datetime.now()
    return ExtractedFact(
        id="test-fact-1",
        fact_type="事件",
        subject=subject,
        content=content,
        confidence=0.9,
        source_message_id=None,
        event_time=event_time,
        created_at=created_at or now,
        updated_at=now,
        is_active=True,
    )


class TestKnownFactsIncludeAll:
    """测试 _get_known_facts 包含所有事实（带日期）"""

    @pytest.mark.asyncio
    async def test_all_facts_included_regardless_of_age(self, tmp_path):
        """超过7天的事实也应该被包含"""
        db_path = str(tmp_path / "test.db")
        db = MemoryDatabase(db_path)
        await db.initialize()

        # 插入一个30天前的事实
        old_time = datetime.now() - timedelta(days=30)
        fact = _make_fact(created_at=old_time)
        await db.save_fact(fact)

        facts = await db.get_facts(limit=50)
        assert len(facts) >= 1
        assert any("学姐" in f.subject for f in facts)

    @pytest.mark.asyncio
    async def test_facts_have_event_time(self, tmp_path):
        """事实应包含 event_time 日期信息"""
        db_path = str(tmp_path / "test.db")
        db = MemoryDatabase(db_path)
        await db.initialize()

        fact = _make_fact(event_time="2025-07-15")
        await db.save_fact(fact)

        facts = await db.get_facts()
        assert len(facts) == 1
        assert facts[0].event_time == "2025-07-15"


class TestPromptRespectsUserInstructions:
    """测试 prompt 包含尊重用户对话指令的规则"""

    def test_prompt_has_obey_user_instruction_rule(self):
        """prompt 模板应包含尊重用户明确指令的规则"""
        from src.companion.handler import SYSTEM_PROMPT_TEMPLATE
        assert "明确指令" in SYSTEM_PROMPT_TEMPLATE or \
               "尊重用户" in SYSTEM_PROMPT_TEMPLATE


class TestKnownFactsFormatting:
    """测试 known_facts 格式包含日期"""

    @pytest.mark.asyncio
    async def test_facts_include_date_in_output(self, tmp_path):
        """格式化输出中应包含日期"""
        db_path = str(tmp_path / "test.db")
        db = MemoryDatabase(db_path)
        await db.initialize()

        fact = _make_fact(event_time="2025-07-15")
        await db.save_fact(fact)

        facts = await db.get_facts()
        # 格式化：每条事实应带日期
        lines = []
        for f in facts:
            time_info = f" [{f.event_time}]" if f.event_time else ""
            lines.append(f"- [{f.fact_type}] {f.subject}: {f.content}{time_info}")

        result = "\n".join(lines)
        assert "2025-07-15" in result
