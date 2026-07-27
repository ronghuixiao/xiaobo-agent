"""日报生成 Skill — 自动生成今日日报"""
from datetime import datetime

from ..base import BaseSkill, SkillContext, SkillResult


class DailyReportSkill(BaseSkill):
    """日报生成技能"""
    
    @property
    def name(self) -> str:
        return "daily_report"
    
    @property
    def description(self) -> str:
        return "自动生成今日日报，包含对话回顾、情绪分析、任务完成情况"
    
    @property
    def triggers(self) -> list:
        return ["日报", "今天总结", "今日总结", "生成日报", "今天做了什么"]
    
    @property
    def priority(self) -> int:
        return 5  # 高优先级
    
    async def execute(self, ctx: SkillContext) -> SkillResult:
        """生成日报"""
        if not ctx.llm or not ctx.memory:
            return SkillResult(success=False, error="缺少 LLM 或 Memory 依赖")
        
        try:
            from src.companion.daily_report import DailyReportGenerator
            reporter = DailyReportGenerator(ctx.llm, ctx.memory)
            report = await reporter.generate_daily_report()
            return SkillResult(success=True, content=report)
        except Exception as e:
            return SkillResult(success=False, error=str(e))
