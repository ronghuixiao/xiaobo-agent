"""信息抽取器

从对话中自动提取结构化信息：
- 事实（人物、偏好、能力、目标等）
- 情绪
- 主题标签

使用 LLM 进行抽取，结果存入记忆数据库。
"""

import json
import logging
from typing import List, Optional, Tuple

from src.llm.base import ChatMessage, LLMProvider
from src.memory.base import (
    ConversationMessage,
    EmotionRecord,
    EmotionType,
    ExtractedFact,
    FactType,
)

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """你是一个信息抽取助手。从用户的对话消息中提取结构化信息。

用户的消息：
"{message}"

请提取以下信息，返回 JSON 格式：
{{
  "facts": [
    {{
      "fact_type": "person|preference|ability|goal|habit|event|commitment|opinion",
      "subject": "关于什么",
      "content": "具体内容",
      "confidence": 0.0-1.0
    }}
  ],
  "emotion": {{
    "type": "happy|sad|anxious|excited|calm|frustrated|tired|neutral",
    "intensity": 0.0-1.0,
    "context": "什么情境下产生的"
  }},
  "topics": ["话题标签1", "话题标签2"]
}}

规则：
- 只提取明确提到的信息，不要猜测
- fact_type 对应：person=人物关系, preference=偏好, ability=能力, goal=目标, habit=习惯, event=事件, commitment=承诺/计划, opinion=观点
- 情绪判断要结合语境，不要只看关键词
- 话题标签用中文，简洁明了
- 如果没有值得提取的信息，返回空数组
- 只返回 JSON，不要其他文字
"""


class MessageExtractor:
    """对话信息抽取器"""

    def __init__(self, llm: LLMProvider):
        self.llm = llm

    async def extract(
        self, message: ConversationMessage
    ) -> Tuple[List[ExtractedFact], Optional[EmotionRecord], List[str]]:
        """从消息中提取信息

        Returns:
            (facts, emotion_record, topics)
        """
        prompt = EXTRACTION_PROMPT.format(message=message.content)

        try:
            response = await self.llm.chat(
                messages=[ChatMessage(role="user", content=prompt)],
                temperature=0.1,  # 低温度保证抽取一致性
                max_tokens=1024,
            )

            # 解析 JSON
            content = response.content.strip()
            # 去掉可能的 markdown 代码块
            if content.startswith("```"):
                content = content.split("\n", 1)[1]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()

            data = json.loads(content)

            # 构建事实列表
            facts = []
            for f in data.get("facts", []):
                facts.append(ExtractedFact(
                    fact_type=f.get("fact_type", "event"),
                    subject=f.get("subject", ""),
                    content=f.get("content", ""),
                    confidence=f.get("confidence", 0.8),
                    source_message_id=message.id,
                ))

            # 构建情绪记录
            emotion_data = data.get("emotion", {})
            emotion_record = None
            if emotion_data and emotion_data.get("type", "neutral") != "neutral":
                emotion_record = EmotionRecord(
                    emotion=emotion_data.get("type", "neutral"),
                    intensity=emotion_data.get("intensity", 0.5),
                    context=emotion_data.get("context", ""),
                    source_message_id=message.id,
                    timestamp=message.timestamp,
                )

            # 话题标签
            topics = data.get("topics", [])

            return facts, emotion_record, topics

        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"信息抽取解析失败: {e}")
            return [], None, []
        except Exception as e:
            logger.error(f"信息抽取异常: {e}")
            return [], None, []
