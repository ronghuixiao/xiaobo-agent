"""记忆查询工具 — 查询用户的长期记忆"""
from typing import Any, Optional

from ..base import BaseTool, ToolParameter, ToolResult


class MemoryQueryTool(BaseTool):
    """记忆查询工具"""
    
    def __init__(self, memory=None):
        self._memory = memory
    
    @property
    def name(self) -> str:
        return "query_memory"
    
    @property
    def description(self) -> str:
        return "查询关于用户的长期记忆。可以查询用户偏好、习惯、目标、历史事件等。当用户问'我之前说过什么'、'我喜欢什么'、'我的目标是什么'时使用。"
    
    @property
    def parameters(self) -> list:
        return [
            ToolParameter(
                name="query",
                type="string",
                description="查询关键词，如 'Python'、'学习习惯'、'目标'",
                required=True
            ),
            ToolParameter(
                name="fact_type",
                type="string",
                description="过滤事实类型：preference/habit/goal/event/person/opinion/全部",
                required=False,
                default="全部"
            )
        ]
    
    async def execute(self, query: str, fact_type: str = "全部", **kwargs) -> ToolResult:
        if not self._memory:
            return ToolResult(success=False, error="记忆系统未初始化")
        
        try:
            # 查询事实
            facts = await self._memory.get_facts(limit=200)
            
            # 过滤
            results = []
            for f in facts:
                # 类型过滤
                if fact_type != "全部" and f.fact_type != fact_type:
                    continue
                # 关键词匹配
                text = f"{f.subject} {f.content}".lower()
                if query.lower() in text:
                    results.append({
                        "type": f.fact_type,
                        "subject": f.subject,
                        "content": f.content,
                        "confidence": round(f.confidence, 2),
                    })
            
            return ToolResult(
                success=True,
                data={
                    "query": query,
                    "total_facts": len(facts),
                    "matched": len(results),
                    "results": results[:10],  # 最多返回10条
                }
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
