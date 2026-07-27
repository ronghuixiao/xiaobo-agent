"""Tool 注册中心 — 管理所有可用工具

设计模式：注册表模式（Registry Pattern）
- 工具自注册：每个 Tool 实例注册到 Registry
- 按名称查找：O(1) 复杂度
- 批量导出 schema：给 LLM 看的工具描述
"""
import logging
from typing import Any, Dict, List, Optional

from .base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class ToolRegistry:
    """工具注册中心"""
    
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
    
    def register(self, tool: BaseTool) -> None:
        """注册工具"""
        if tool.name in self._tools:
            logger.warning(f"工具 {tool.name} 已存在，将被覆盖")
        self._tools[tool.name] = tool
        logger.info(f"✅ 注册工具: {tool.name} - {tool.description[:30]}")
    
    def unregister(self, name: str) -> None:
        """注销工具"""
        if name in self._tools:
            del self._tools[name]
            logger.info(f"❌ 注销工具: {name}")
    
    def get(self, name: str) -> Optional[BaseTool]:
        """按名称获取工具"""
        return self._tools.get(name)
    
    def list_tools(self) -> List[BaseTool]:
        """获取所有已注册工具"""
        return list(self._tools.values())
    
    def to_schemas(self) -> List[Dict]:
        """导出所有工具的JSON Schema（给LLM看）"""
        return [tool.to_schema() for tool in self._tools.values()]
    
    def to_prompt_section(self) -> str:
        """生成工具描述文本，注入系统提示"""
        if not self._tools:
            return ""
        
        lines = ["## 可用工具", ""]
        lines.append("当用户需要以下能力时，你可以调用对应工具。工具调用格式：")
        lines.append("```json")
        lines.append('{"tool": "工具名", "args": {"参数名": "参数值"}}')
        lines.append("```")
        lines.append("")
        lines.append("规则：")
        lines.append("- 只有用户明确需要时才调用工具，不要主动调用")
        lines.append("- 一次可以调用一个工具")
        lines.append("- 工具结果会自动返回给你，你可以基于结果回复用户")
        lines.append("- 如果不需要工具，直接回复即可")
        lines.append("")
        
        for tool in self._tools.values():
            lines.append(f"### {tool.name}")
            lines.append(f"描述: {tool.description}")
            if tool.parameters:
                lines.append("参数:")
                for p in tool.parameters:
                    req = "必填" if p.required else "可选"
                    lines.append(f"  - {p.name} ({p.type}, {req}): {p.description}")
            lines.append("")
        
        return "\n".join(lines)
    
    async def execute(self, tool_name: str, args: Dict[str, Any]) -> ToolResult:
        """执行工具"""
        tool = self._tools.get(tool_name)
        if not tool:
            return ToolResult(
                success=False,
                error=f"工具 '{tool_name}' 不存在。可用工具: {list(self._tools.keys())}"
            )
        
        try:
            logger.info(f"🔧 调用工具: {tool_name}({args})")
            result = await tool.execute(**args)
            logger.info(f"✅ 工具结果: {tool_name} → success={result.success}")
            return result
        except Exception as e:
            logger.error(f"❌ 工具执行失败: {tool_name} → {e}")
            return ToolResult(success=False, error=str(e))
