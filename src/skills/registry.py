"""Skill 注册中心 — 管理所有已注册的 Skill"""
import logging
from typing import Dict, List, Optional

from .base import BaseSkill, SkillResult, SkillContext

logger = logging.getLogger(__name__)


class SkillRegistry:
    """Skill 注册中心"""
    
    def __init__(self):
        self._skills: Dict[str, BaseSkill] = {}
    
    def register(self, skill: BaseSkill) -> None:
        """注册 Skill"""
        if skill.name in self._skills:
            logger.warning(f"Skill {skill.name} 已存在，将被覆盖")
        self._skills[skill.name] = skill
        logger.info(f"🎯 注册 Skill: {skill.name} (triggers={skill.triggers})")
    
    def unregister(self, name: str) -> None:
        """注销 Skill"""
        if name in self._skills:
            del self._skills[name]
    
    def get(self, name: str) -> Optional[BaseSkill]:
        """按名称获取"""
        return self._skills.get(name)
    
    def list_skills(self) -> List[BaseSkill]:
        """获取所有 Skill"""
        return list(self._skills.values())
    
    def match(self, message: str) -> Optional[BaseSkill]:
        """匹配消息，返回第一个命中的 Skill（按优先级排序）"""
        candidates = [s for s in self._skills.values() if s.matches(message)]
        if not candidates:
            return None
        # 按优先级排序（数字越小越优先）
        candidates.sort(key=lambda s: s.priority)
        return candidates[0]
    
    def match_all(self, message: str) -> List[BaseSkill]:
        """匹配消息，返回所有命中的 Skill"""
        candidates = [s for s in self._skills.values() if s.matches(message)]
        candidates.sort(key=lambda s: s.priority)
        return candidates
    
    async def execute(self, skill: BaseSkill, ctx: SkillContext) -> SkillResult:
        """执行 Skill"""
        try:
            logger.info(f"🎯 执行 Skill: {skill.name}")
            result = await skill.execute(ctx)
            logger.info(f"✅ Skill {skill.name} 完成: success={result.success}")
            return result
        except Exception as e:
            logger.error(f"❌ Skill {skill.name} 执行失败: {e}")
            return SkillResult(success=False, error=str(e))
    
    def to_prompt_section(self) -> str:
        """生成 Skill 描述文本（给 LLM 看）"""
        if not self._skills:
            return ""
        lines = ["## 可用技能（Skills）", ""]
        lines.append("以下技能可以自动触发。当用户消息匹配关键词时，系统会自动执行对应技能。")
        lines.append("")
        for skill in self._skills.values():
            lines.append(f"- **{skill.name}**: {skill.description}")
            lines.append(f"  触发词: {', '.join(skill.triggers)}")
        return "\n".join(lines)
