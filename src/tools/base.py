"""Tool 基类 — 所有工具的抽象接口

设计原则：
- 每个 Tool 是自包含的：定义名称、描述、参数schema、执行逻辑
- Tool 不感知 LLM，只负责接收参数、返回结果
- Tool 可以是同步或异步的
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from pydantic import BaseModel


class ToolParameter(BaseModel):
    """工具参数定义"""
    name: str
    type: str  # "string", "number", "boolean"
    description: str
    required: bool = True
    default: Any = None


class ToolResult(BaseModel):
    """工具执行结果"""
    success: bool
    data: Any = None
    error: Optional[str] = None


class BaseTool(ABC):
    """工具基类"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称（唯一标识）"""
        ...
    
    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述（给LLM看的）"""
        ...
    
    @property
    @abstractmethod
    def parameters(self) -> list[ToolParameter]:
        """参数定义列表"""
        ...
    
    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """执行工具"""
        ...
    
    def to_schema(self) -> Dict:
        """转换为JSON Schema格式（给LLM看的）"""
        props = {}
        required = []
        for p in self.parameters:
            props[p.name] = {
                "type": p.type,
                "description": p.description,
            }
            if p.default is not None:
                props[p.name]["default"] = p.default
            if p.required:
                required.append(p.name)
        
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": props,
                "required": required,
            }
        }
