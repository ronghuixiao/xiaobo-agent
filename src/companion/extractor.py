"""信息抽取器

从对话中自动提取结构化信息：
- 事实（人物、偏好、能力、目标等）
- 情绪
- 主题标签
- 学习内容（LLM智能识别，非关键词匹配）

使用 LLM 进行抽取，结果存入记忆数据库。
一次 LLM 调用完成所有抽取，不增加额外延迟。
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

当前时间：{current_time}

请提取以下信息，返回 JSON 格式：
{{
  "facts": [
    {{
      "fact_type": "person|preference|ability|goal|habit|event|commitment|opinion",
      "subject": "关于什么",
      "content": "具体内容",
      "confidence": 0.0-1.0,
      "event_time": "事件发生时间（绝对时间）"
    }}
  ],
  "emotion": {{
    "type": "happy|sad|anxious|excited|calm|frustrated|tired|neutral",
    "intensity": 0.0-1.0,
    "context": "什么情境下产生的"
  }},
  "topics": ["话题标签1", "话题标签2"],
  "is_learning": true/false,
  "learning_info": {{
    "topic": "学习主题",
    "content": "具体学了什么/做了什么/研究了什么",
    "understanding": "理解程度（初步了解/基本掌握/完全理解/实践应用）",
    "tags": "标签1,标签2"
  }}
}}

## 判断 is_learning 的规则（非常重要）：
以下情况都算学习/工作/技术实践，is_learning 应为 true：
- 明确说"学了/看了/读了/做了" → true
- 讨论技术实现："我在做skill系统"、"我在研究tool calling"、"我在优化项目" → true
- 描述工程实践："刚把RAG重构了"、"在调试memory模块"、"在写测试" → true
- 分享技术理解："我理解了事件循环"、"搞懂了依赖注入" → true
- 讨论设计方案："我在设计一个缓存策略"、"在考虑用什么数据库" → true
- 日常闲聊、情绪表达、询问时间等 → false

## learning_info 字段说明：
- 只有 is_learning 为 true 时才填写
- topic: 简短的主题名（如：Tool Calling实现、RAG优化、Skill系统设计）
- content: 具体做了什么/学了什么（一句话描述）
- understanding: 从消息推断的理解程度
- tags: 相关标签（逗号分隔，如：agent,架构,python）

## 其他规则：
- 只提取明确提到的信息，不要猜测
- fact_type 对应：person=人物关系, preference=偏好, ability=能力, goal=目标, habit=习惯, event=事件, commitment=承诺/计划, opinion=观点
- **重要：event_time必须使用绝对时间，不要使用"昨晚"、"前天"、"刚才"等相对时间词**
- 情绪判断要结合语境，不要只看关键词
- 话题标签用中文，简洁明了
- 如果没有值得提取的信息，返回空数组和false
- 只返回 JSON，不要其他文字
"""


class MessageExtractor:
    """对话信息抽取器"""

    def __init__(self, llm: LLMProvider):
        self.llm = llm

    async def extract(
        self, message: ConversationMessage
    ) -> Tuple[List[ExtractedFact], Optional[EmotionRecord], List[str], bool, Optional[dict]]:
        """从消息中提取信息

        Returns:
            (facts, emotion_record, topics, is_learning, learning_info)
        """
        from datetime import datetime
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        prompt = EXTRACTION_PROMPT.format(message=message.content, current_time=current_time)

        try:
            response = await self.llm.chat(
                messages=[ChatMessage(role="user", content=prompt)],
                temperature=0.1,  # 低温度保证抽取一致性
                max_tokens=2048,  # Mimo 推理模型需要更多 token（含思考过程）
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
                    event_time=f.get("event_time"),
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

            # 学习内容识别（LLM智能判断，非关键词匹配）
            is_learning = data.get("is_learning", False)
            learning_info = data.get("learning_info", None)
            if is_learning and learning_info and not learning_info.get("topic"):
                is_learning = False
                learning_info = None

            return facts, emotion_record, topics, is_learning, learning_info

        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"信息抽取解析失败: {e}")
            return [], None, [], False, None
        except Exception as e:
            logger.error(f"信息抽取异常: {e}")
            return [], None, [], False, None
