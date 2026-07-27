"""情绪分析 Skill — 分析并记录用户情绪"""
from datetime import datetime

from ..base import BaseSkill, SkillContext, SkillResult


class MoodAnalysisSkill(BaseSkill):
    """情绪分析技能"""
    
    @property
    def name(self) -> str:
        return "mood_analysis"
    
    @property
    def description(self) -> str:
        return "分析用户情绪状态，记录情绪变化趋势"
    
    @property
    def triggers(self) -> list:
        return ["心情", "情绪", "感觉", "开心", "难过", "焦虑", "压力大", 
                "累", "烦", "高兴", "兴奋", "沮丧", "无聊"]
    
    @property
    def priority(self) -> int:
        return 9
    
    async def execute(self, ctx: SkillContext) -> SkillResult:
        """分析情绪"""
        if not ctx.llm or not ctx.memory:
            return SkillResult(success=False, error="缺少 LLM 或 Memory 依赖")
        
        try:
            prompt = f"""分析以下消息的情绪，返回JSON：
消息："{ctx.user_message}"

返回格式：
{{"emotion": "happy/sad/anxious/excited/calm/frustrated/tired/neutral", "intensity": 0.0-1.0, "context": "触发情境"}}

只返回JSON。emotion必须是括号中的一个。"""
            
            from src.llm.base import ChatMessage
            response = await ctx.llm.chat(
                messages=[ChatMessage(role="user", content=prompt)],
                temperature=0.1,
                max_tokens=256,
            )
            
            import json
            data = json.loads(response.content.strip().strip('`').strip())
            
            from src.memory.base import EmotionRecord
            emotion_record = EmotionRecord(
                emotion=data.get("emotion", "neutral"),
                intensity=data.get("intensity", 0.5),
                context=data.get("context", ""),
                source_message_id="",
                timestamp=datetime.now(),
            )
            await ctx.memory.save_emotion(emotion_record)
            
            emoji_map = {"happy":"😊","sad":"😢","anxious":"😰","excited":"🤩",
                         "calm":"😌","frustrated":"😠","tired":"😴","neutral":"😐"}
            emoji = emoji_map.get(emotion_record.emotion, "❓")
            
            return SkillResult(
                success=True,
                content=f"{emoji} 情绪已记录：{emotion_record.emotion} (强度: {emotion_record.intensity})",
                data={"emotion": emotion_record.emotion, "intensity": emotion_record.intensity}
            )
        except Exception as e:
            return SkillResult(success=False, error=str(e))
