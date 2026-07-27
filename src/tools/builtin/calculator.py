"""计算器工具 — 安全的数学表达式求值"""
import ast
import operator
import math
from typing import Any

from ..base import BaseTool, ToolParameter, ToolResult


# 安全的运算符映射
SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

SAFE_FUNCTIONS = {
    "abs": abs,
    "round": round,
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "log10": math.log10,
    "pi": math.pi,
    "e": math.e,
}


def safe_eval(node):
    """安全地求值AST节点"""
    if isinstance(node, ast.Expression):
        return safe_eval(node.body)
    elif isinstance(node, ast.Constant):
        return node.value
    elif isinstance(node, ast.BinOp):
        op = SAFE_OPERATORS.get(type(node.op))
        if op:
            return op(safe_eval(node.left), safe_eval(node.right))
    elif isinstance(node, ast.UnaryOp):
        op = SAFE_OPERATORS.get(type(node.op))
        if op:
            return op(safe_eval(node.operand))
    elif isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in SAFE_FUNCTIONS:
            func = SAFE_FUNCTIONS[node.func.id]
            args = [safe_eval(arg) for arg in node.args]
            return func(*args)
    raise ValueError(f"不支持的表达式: {ast.dump(node)}")


class CalculatorTool(BaseTool):
    """计算器工具"""
    
    @property
    def name(self) -> str:
        return "calculate"
    
    @property
    def description(self) -> str:
        return "计算数学表达式。支持加减乘除、幂运算、三角函数等。当用户需要计算时使用。"
    
    @property
    def parameters(self) -> list:
        return [
            ToolParameter(
                name="expression",
                type="string",
                description="数学表达式，如 '2+3*4'、'sqrt(16)'、'sin(pi/2)'",
                required=True
            )
        ]
    
    async def execute(self, expression: str, **kwargs) -> ToolResult:
        try:
            tree = ast.parse(expression, mode='eval')
            result = safe_eval(tree)
            return ToolResult(
                success=True,
                data={"expression": expression, "result": result}
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"计算失败: {str(e)}"
            )
