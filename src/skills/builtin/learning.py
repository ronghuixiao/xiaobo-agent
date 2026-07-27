"""学习记录 Skill — 自动提取并记录学习内容"""
from datetime import datetime
from typing import List

from ..base import BaseSkill, SkillContext, SkillResult


class LearningRecordSkill(BaseSkill):
    """学习记录技能"""
    
    @property
    def name(self) -> str:
        return "learning_record"
    
    @property
    def description(self) -> str:
        return "自动提取学习内容并记录，包含主题、理解程度、关联知识点"
    
    @property
    def triggers(self) -> list:
        return ["学了", "学习了", "看书了", "做了笔记", "搞懂了", "理解了", 
                "刷完题", "学完", "掌握了", "复习了"]
    
    @property
    def priority(self) -> int:
        return 8
    
    async def execute(self, ctx: SkillContext) -> SkillResult:
        """提取学习内容并记录"""
        if not ctx.llm or not ctx.memory:
            return SkillResult(success=False, error="缺少 LLM 或 Memory 依赖")
        
        try:
            # 用 LLM 提取学习信息
            prompt = f"""从以下消息中提取学习信息，返回JSON：
消息："{ctx.user_message}"

返回格式：
{{"topic": "学习主题", "content": "具体学了什么", "understanding": "理解程度", "tags": "标签1,标签2"}}

只返回JSON。"""
            
            from src.llm.base import ChatMessage
            response = await ctx.llm.chat(
                messages=[ChatMessage(role="user", content=prompt)],
                temperature=0.1,
                max_tokens=512,
            )
            
            import json
            data = json.loads(response.content.strip().strip('`').strip())
            
            if not data.get("topic"):
                return SkillResult(success=False, error="未提取到学习主题")
            
            # 保存到 learning_log
            record = {
                "topic": data["topic"],
                "content": data.get("content", ""),
                "understanding": data.get("understanding", ""),
                "related_topics": data.get("related_topics", ""),
                "tags": data.get("tags", ""),
                "source_message_id": "",
                "created_at": datetime.now().isoformat(),
            }
            await ctx.memory.save_learning_record(record)
            
            return SkillResult(
                success=True,
                content=f"📚 学习记录已保存：{data['topic']}",
                data=record
            )
        except Exception as e:
            return SkillResult(success=False, error=str(e))
