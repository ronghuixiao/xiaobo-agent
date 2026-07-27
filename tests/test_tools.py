"""Tool 系统测试"""
import pytest
import asyncio
from src.tools import BaseTool, ToolParameter, ToolResult, ToolRegistry, ToolExecutor
from src.tools.builtin import TimeTool, CalculatorTool, MemoryQueryTool


# === 测试工具基类 ===

class DummyTool(BaseTool):
    """测试用虚拟工具"""
    @property
    def name(self): return "dummy"
    @property
    def description(self): return "测试工具"
    @property
    def parameters(self):
        return [ToolParameter(name="text", type="string", description="输入文本")]
    async def execute(self, text="", **kwargs):
        return ToolResult(success=True, data={"echo": text})


def test_tool_schema():
    """测试工具Schema生成"""
    tool = DummyTool()
    schema = tool.to_schema()
    assert schema["name"] == "dummy"
    assert schema["description"] == "测试工具"
    assert "text" in schema["parameters"]["properties"]
    assert "text" in schema["parameters"]["required"]


@pytest.mark.asyncio
async def test_tool_execute():
    """测试工具执行"""
    tool = DummyTool()
    result = await tool.execute(text="hello")
    assert result.success is True
    assert result.data["echo"] == "hello"


# === 测试注册中心 ===

def test_registry_register():
    """测试工具注册"""
    registry = ToolRegistry()
    tool = DummyTool()
    registry.register(tool)
    assert registry.get("dummy") is tool
    assert len(registry.list_tools()) == 1


def test_registry_not_found():
    """测试工具不存在"""
    registry = ToolRegistry()
    assert registry.get("nonexistent") is None


def test_registry_schemas():
    """测试批量Schema导出"""
    registry = ToolRegistry()
    registry.register(DummyTool())
    schemas = registry.to_schemas()
    assert len(schemas) == 1
    assert schemas[0]["name"] == "dummy"


def test_registry_prompt_section():
    """测试Prompt段落生成"""
    registry = ToolRegistry()
    registry.register(DummyTool())
    section = registry.to_prompt_section()
    assert "可用工具" in section
    assert "dummy" in section
    assert "测试工具" in section


# === 测试内置工具 ===

@pytest.mark.asyncio
async def test_time_tool():
    """测试时间工具"""
    tool = TimeTool()
    result = await tool.execute()
    assert result.success is True
    assert "datetime" in result.data
    assert "weekday" in result.data


@pytest.mark.asyncio
async def test_time_tool_format():
    """测试时间工具格式"""
    tool = TimeTool()
    result = await tool.execute(format="time")
    assert result.success is True
    assert "time" in result.data


@pytest.mark.asyncio
async def test_calculator_tool():
    """测试计算器工具"""
    tool = CalculatorTool()
    result = await tool.execute(expression="2+3*4")
    assert result.success is True
    assert result.data["result"] == 14


@pytest.mark.asyncio
async def test_calculator_tool_math():
    """测试计算器数学函数"""
    tool = CalculatorTool()
    result = await tool.execute(expression="sqrt(16)")
    assert result.success is True
    assert result.data["result"] == 4.0


@pytest.mark.asyncio
async def test_calculator_tool_invalid():
    """测试计算器无效表达式"""
    tool = CalculatorTool()
    result = await tool.execute(expression="import os")
    assert result.success is False
    assert result.error is not None


# === 测试执行器 ===

def test_executor_parse_tool_calls():
    """测试工具调用解析"""
    registry = ToolRegistry()
    executor = ToolExecutor(registry)
    
    text = '''一些文字
```json
{"tool": "calculate", "args": {"expression": "2+2"}}
```
更多文字'''
    
    calls = executor.parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0]["tool"] == "calculate"
    assert calls[0]["args"]["expression"] == "2+2"


def test_executor_parse_plain_json():
    """测试解析裸JSON"""
    registry = ToolRegistry()
    executor = ToolExecutor(registry)
    
    text = '{"tool": "time", "args": {"format": "full"}}'
    calls = executor.parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0]["tool"] == "time"


def test_executor_no_tool_calls():
    """测试无工具调用"""
    registry = ToolRegistry()
    executor = ToolExecutor(registry)
    
    text = "今天天气真好，没有工具调用"
    assert executor.has_tool_calls(text) is False
    calls = executor.parse_tool_calls(text)
    assert len(calls) == 0


def test_executor_clean_tool_calls():
    """测试清理工具调用标记"""
    registry = ToolRegistry()
    executor = ToolExecutor(registry)
    
    text = '''回复内容
```json
{"tool": "calculate", "args": {"expression": "1+1"}}
```
后续内容'''
    
    cleaned = executor.clean_tool_calls(text)
    assert "calculate" not in cleaned
    assert "回复内容" in cleaned


@pytest.mark.asyncio
async def test_executor_execute_calls():
    """测试执行工具调用"""
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    executor = ToolExecutor(registry)
    
    calls = [{"tool": "calculate", "args": {"expression": "10*10"}}]
    results = await executor.execute_calls(calls)
    assert len(results) == 1
    assert results[0]["success"] is True
    assert results[0]["data"]["result"] == 100


@pytest.mark.asyncio
async def test_executor_execute_unknown_tool():
    """测试执行未知工具"""
    registry = ToolRegistry()
    executor = ToolExecutor(registry)
    
    calls = [{"tool": "nonexistent", "args": {}}]
    results = await executor.execute_calls(calls)
    assert len(results) == 1
    assert results[0]["success"] is False


def test_executor_format_results():
    """测试结果格式化"""
    registry = ToolRegistry()
    executor = ToolExecutor(registry)
    
    results = [
        {"tool": "calculate", "args": {}, "success": True, "data": {"result": 42}, "error": None},
        {"tool": "time", "args": {}, "success": False, "data": None, "error": "timeout"},
    ]
    
    context = executor.format_results_for_context(results)
    assert "工具调用结果" in context
    assert "calculate" in context
    assert "42" in context
    assert "timeout" in context


@pytest.mark.asyncio
async def test_executor_process_with_tools():
    """测试完整工具处理流程"""
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    executor = ToolExecutor(registry)
    
    text = '''我来算一下
```json
{"tool": "calculate", "args": {"expression": "3*7"}}
```
'''
    
    has_calls, results, cleaned = await executor.process_with_tools(text)
    assert has_calls is True
    assert len(results) == 1
    assert results[0]["success"] is True
    assert "calculate" not in cleaned
