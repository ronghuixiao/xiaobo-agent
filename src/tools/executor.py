"""Tool 执行器 — 解析LLM工具调用 + 执行 + 结果回注

流程：
1. LLM输出包含工具调用的回复
2. Executor解析JSON提取工具名和参数
3. 执行工具获取结果
4. 将结果格式化为上下文注入LLM
5. LLM基于工具结果生成最终回复
"""
import json
import re
import logging
from typing import Dict, List, Optional, Tuple

from .base import ToolResult
from .registry import ToolRegistry

logger = logging.getLogger(__name__)


class ToolExecutor:
    """工具执行器"""
    
    # 工具调用的正则模式
    # 匹配 ```json\n{"tool": "xxx", "args": {...}}\n``` 或裸JSON
    TOOL_CALL_PATTERN = re.compile(
        r'```json\s*\n(\{.*?\})\s*\n```|'
        r'(\{"tool"\s*:\s*".*?"\s*,\s*"args"\s*:\s*\{.*?\}\})',
        re.DOTALL
    )
    
    def __init__(self, registry: ToolRegistry, max_rounds: int = 3):
        """
        Args:
            registry: 工具注册中心
            max_rounds: 最大工具调用轮数（防止无限循环）
        """
        self.registry = registry
        self.max_rounds = max_rounds
    
    def parse_tool_calls(self, text: str) -> List[Dict]:
        """从LLM输出中解析工具调用"""
        calls = []
        for match in self.TOOL_CALL_PATTERN.finditer(text):
            json_str = match.group(1) or match.group(2)
            try:
                data = json.loads(json_str)
                if "tool" in data and "args" in data:
                    calls.append(data)
            except json.JSONDecodeError:
                continue
        return calls
    
    def has_tool_calls(self, text: str) -> bool:
        """检查文本中是否包含工具调用"""
        return bool(self.TOOL_CALL_PATTERN.search(text))
    
    def clean_tool_calls(self, text: str) -> str:
        """清理文本中的工具调用标记，只保留自然语言部分"""
        return self.TOOL_CALL_PATTERN.sub('', text).strip()
    
    async def execute_calls(self, calls: List[Dict]) -> List[Dict]:
        """执行所有工具调用，返回结果列表"""
        results = []
        for call in calls[:self.max_rounds]:  # 限制轮数
            tool_name = call.get("tool", "")
            args = call.get("args", {})
            
            result = await self.registry.execute(tool_name, args)
            results.append({
                "tool": tool_name,
                "args": args,
                "success": result.success,
                "data": result.data,
                "error": result.error,
            })
        return results
    
    def format_results_for_context(self, results: List[Dict]) -> str:
        """将工具结果格式化为上下文文本，注入LLM"""
        if not results:
            return ""
        
        lines = ["## 工具调用结果", ""]
        for r in results:
            status = "✅" if r["success"] else "❌"
            lines.append(f"### {status} {r['tool']}")
            if r["success"]:
                # 结果可能是字符串或dict
                data = r["data"]
                if isinstance(data, str):
                    lines.append(data)
                elif isinstance(data, dict):
                    for k, v in data.items():
                        lines.append(f"- {k}: {v}")
                else:
                    lines.append(str(data))
            else:
                lines.append(f"错误: {r['error']}")
            lines.append("")
        
        return "\n".join(lines)
    
    async def process_with_tools(self, llm_text: str) -> Tuple[bool, List[Dict], str]:
        """处理LLM输出中的工具调用
        
        Returns:
            (has_calls, results, cleaned_text)
            - has_calls: 是否包含工具调用
            - results: 工具执行结果列表
            - cleaned_text: 清理后的自然语言文本
        """
        calls = self.parse_tool_calls(llm_text)
        if not calls:
            return False, [], llm_text
        
        results = await self.execute_calls(calls)
        cleaned = self.clean_tool_calls(llm_text)
        return True, results, cleaned
