"""Skill 基类 — 可插拔的高级能力抽象

Skill vs Tool 的区别：
- Tool = 底层能力（查时间、算数学、查记忆），无状态，一次调用返回结果
- Skill = 高级能力（日报生成、学习记录、情绪分析），有状态，编排多个步骤

一个 Skill 可以：
1. 匹配用户意图（trigger）
2. 调用 Tool 执行底层操作
3. 调用 LLM 生成内容
4. 访问记忆系统
5. 返回结构化结果
"""
import re
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class SkillResult(BaseModel):
    """Skill 执行结果"""
    success: bool
    content: str = ""  # 回复内容
    data: Any = None   # 附加数据
    error: Optional[str] = None


class SkillContext(BaseModel):
    """Skill 执行上下文 — 传递给 Skill 的所有依赖"""
    user_message: str
    llm: Any = None           # LLMProvider
    memory: Any = None        # MemoryDatabase
    tools: Any = None         # ToolRegistry
    settings: Any = None      # Settings


class BaseSkill(ABC):
    """Skill 基类"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Skill 唯一标识"""
        ...
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Skill 描述"""
        ...
    
    @property
    @abstractmethod
    def triggers(self) -> List[str]:
        """触发关键词列表 — 用户消息包含任一关键词即触发"""
        ...
    
    @property
    def priority(self) -> int:
        """优先级，数字越小越优先（默认10）"""
        return 10
    
    def matches(self, message: str) -> bool:
        """检查消息是否触发此 Skill"""
        msg = message.strip().lower()
        return any(t.lower() in msg for t in self.triggers)
    
    @abstractmethod
    async def execute(self, ctx: SkillContext) -> SkillResult:
        """执行 Skill"""
        ...
    
    def __repr__(self):
        return f"<Skill: {self.name}>"
