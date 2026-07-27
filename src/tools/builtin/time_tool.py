"""时间工具 — 获取当前时间、日期、时区"""
from datetime import datetime
from typing import Any

from ..base import BaseTool, ToolParameter, ToolResult


class TimeTool(BaseTool):
    """时间查询工具"""
    
    @property
    def name(self) -> str:
        return "get_time"
    
    @property
    def description(self) -> str:
        return "获取当前时间、日期、星期几。当用户问'现在几点'、'今天星期几'、'今天几号'时使用。"
    
    @property
    def parameters(self) -> list:
        return [
            ToolParameter(
                name="format",
                type="string",
                description="返回格式：'full'(完整日期时间)、'time'(仅时间)、'date'(仅日期)、'weekday'(仅星期)",
                required=False,
                default="full"
            )
        ]
    
    async def execute(self, format: str = "full", **kwargs) -> ToolResult:
        now = datetime.now()
        
        if format == "time":
            data = {"time": now.strftime("%H:%M:%S")}
        elif format == "date":
            data = {"date": now.strftime("%Y-%m-%d"), "display": now.strftime("%Y年%m月%d日")}
        elif format == "weekday":
            weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
            data = {"weekday": weekdays[now.weekday()]}
        else:
            weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
            data = {
                "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
                "display": now.strftime("%Y年%m月%d日 %H:%M"),
                "weekday": weekdays[now.weekday()],
            }
        
        return ToolResult(success=True, data=data)
