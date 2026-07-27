"""Skill 系统测试"""
import pytest
from src.skills import BaseSkill, SkillResult, SkillContext, SkillRegistry
from src.skills.builtin import DailyReportSkill, LearningRecordSkill, MoodAnalysisSkill


# === 测试 Skill 基类 ===

class DummySkill(BaseSkill):
    """测试用虚拟 Skill"""
    @property
    def name(self): return "dummy_skill"
    @property
    def description(self): return "测试技能"
    @property
    def triggers(self): return ["测试", "test"]
    async def execute(self, ctx):
        return SkillResult(success=True, content="测试结果")


def test_skill_matches():
    """测试触发匹配"""
    skill = DummySkill()
    assert skill.matches("这是测试消息") is True
    assert skill.matches("this is a test") is True
    assert skill.matches("今天天气真好") is False


def test_skill_priority():
    """测试优先级"""
    skill = DummySkill()
    assert skill.priority == 10  # 默认优先级


# === 测试注册中心 ===

def test_registry_register():
    """测试注册"""
    registry = SkillRegistry()
    skill = DummySkill()
    registry.register(skill)
    assert registry.get("dummy_skill") is skill
    assert len(registry.list_skills()) == 1


def test_registry_match():
    """测试匹配"""
    registry = SkillRegistry()
    registry.register(DummySkill())
    
    matched = registry.match("这是测试消息")
    assert matched.name == "dummy_skill"
    
    matched = registry.match("今天天气真好")
    assert matched is None


def test_registry_match_priority():
    """测试优先级匹配"""
    class HighPrioritySkill(BaseSkill):
        @property
        def name(self): return "high"
        @property
        def description(self): return "高优先级"
        @property
        def triggers(self): return ["测试"]
        @property
        def priority(self): return 1
        async def execute(self, ctx):
            return SkillResult(success=True)
    
    registry = SkillRegistry()
    registry.register(DummySkill())  # priority=10
    registry.register(HighPrioritySkill())  # priority=1
    
    matched = registry.match("测试消息")
    assert matched.name == "high"  # 高优先级先匹配


def test_registry_match_all():
    """测试匹配所有"""
    registry = SkillRegistry()
    registry.register(DummySkill())
    
    class AnotherSkill(BaseSkill):
        @property
        def name(self): return "another"
        @property
        def description(self): return "另一个"
        @property
        def triggers(self): return ["测试"]
        async def execute(self, ctx):
            return SkillResult(success=True)
    
    registry.register(AnotherSkill())
    matched = registry.match_all("测试消息")
    assert len(matched) == 2


def test_registry_prompt_section():
    """测试 Prompt 段落生成"""
    registry = SkillRegistry()
    registry.register(DummySkill())
    section = registry.to_prompt_section()
    assert "可用技能" in section
    assert "dummy_skill" in section
    assert "测试" in section


# === 测试内置 Skill ===

def test_daily_report_triggers():
    """测试日报 Skill 触发词"""
    skill = DailyReportSkill()
    assert skill.matches("帮我生成日报") is True
    assert skill.matches("今天总结") is True
    assert skill.matches("今天做了什么") is True
    assert skill.matches("天气真好") is False


def test_learning_triggers():
    """测试学习 Skill 触发词"""
    skill = LearningRecordSkill()
    assert skill.matches("我学了Python") is True
    assert skill.matches("看书了") is True
    assert skill.matches("搞懂了事件循环") is True
    assert skill.matches("今天天气好") is False


def test_mood_triggers():
    """测试情绪 Skill 触发词"""
    skill = MoodAnalysisSkill()
    assert skill.matches("今天心情不错") is True
    assert skill.matches("感觉压力好大") is True
    assert skill.matches("有点焦虑") is True
    assert skill.matches("学了Python") is False


def test_skills_no_overlap():
    """测试 Skill 之间没有触发词重叠"""
    skills = [DailyReportSkill(), LearningRecordSkill(), MoodAnalysisSkill()]
    all_triggers = []
    for s in skills:
        for t in s.triggers:
            all_triggers.append((t, s.name))
    
    # 检查没有重复触发词
    trigger_texts = [t[0] for t in all_triggers]
    assert len(trigger_texts) == len(set(trigger_texts)), f"有重复触发词: {trigger_texts}"


@pytest.mark.asyncio
async def test_skill_execute():
    """测试 Skill 执行"""
    skill = DummySkill()
    ctx = SkillContext(user_message="测试消息")
    result = await skill.execute(ctx)
    assert result.success is True
    assert result.content == "测试结果"
