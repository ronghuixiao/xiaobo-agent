"""对话处理器

核心对话流程：
1. 接收用户消息
2. 从记忆中检索相关上下文
3. 构建包含记忆的系统提示
4. 调用 LLM 生成回复
5. 保存对话到记忆
6. 异步提取信息并存入记忆
"""

import logging
import uuid
from datetime import datetime
from typing import List, Optional

from config.settings import Settings
from src.llm.base import ChatMessage, LLMProvider
from src.memory.base import ConversationMessage
from src.memory.database import MemoryDatabase

from .extractor import MessageExtractor

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """你是{companion_name}，{user_name}的个人数字伙伴。

## 你的职责
- 记住{user_name}说过的话、她的偏好、她的目标
- 在合适的时机提起以前的对话，让她感到被记住
- 关心她的情绪，在她焦虑时安抚，在她开心时一起开心
- 帮她记录今天做了什么，提醒她之前说过要做的事
- 用温暖但不油腻的方式交流

## 关于{user_name}的已知信息
{known_facts}

## 最近的对话上下文
{recent_context}

## 注意事项
- 不要一次性列出所有记忆，自然地融入对话
- 如果发现与过去相关的内容，自然地提起
- 保持对话的自然流畅，不要像在读数据库
- **重要：不要猜测时间！如果记忆中没有明确的时间信息，不要自己添加"昨晚"、"前天"、"刚才"等时间词**
- 如果记忆中有event_time字段，使用它来描述时间；如果没有，不要添加时间描述
"""


class ConversationHandler:
    """对话处理器"""

    def __init__(
        self,
        settings: Settings,
        llm: LLMProvider,
        memory: MemoryDatabase,
    ):
        self.settings = settings
        self.llm = llm
        self.memory = memory
        self.extractor = MessageExtractor(llm)
        self._current_session_id: Optional[str] = None

    def start_session(self) -> str:
        """开始新的对话会话"""
        self._current_session_id = str(uuid.uuid4())
        logger.info(f"新会话开始: {self._current_session_id}")
        return self._current_session_id

    async def handle_message(self, user_message: str) -> str:
        """处理用户消息，返回回复

        完整流程：
        1. 保存用户消息
        2. 检索相关记忆
        3. 构建带记忆的系统提示
        4. 调用 LLM
        5. 保存助手回复
        6. 异步提取信息
        """
        if not self._current_session_id:
            self.start_session()

        # 1. 保存用户消息
        user_msg = ConversationMessage(
            session_id=self._current_session_id,
            role="user",
            content=user_message,
            timestamp=datetime.now(),
        )
        await self.memory.save_message(user_msg)

        # 2. 检索相关记忆
        known_facts = await self._get_known_facts()
        recent_context = await self._get_recent_context()

        # 3. 构建系统提示
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            companion_name=self.settings.companion.name,
            user_name=self.settings.companion.user_name,
            known_facts=known_facts,
            recent_context=recent_context,
        )

        # 4. 调用 LLM
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_message),
        ]

        response = await self.llm.chat(messages)

        # 5. 保存助手回复
        assistant_msg = ConversationMessage(
            session_id=self._current_session_id,
            role="assistant",
            content=response.content,
            timestamp=datetime.now(),
        )
        await self.memory.save_message(assistant_msg)

        # 6. 提取信息（fire and forget，不阻塞回复）
        try:
            facts, emotion, topics = await self.extractor.extract(user_msg)
            for fact in facts:
                await self.memory.save_fact(fact)
            if emotion:
                await self.memory.save_emotion(emotion)
            if topics:
                from src.memory.base import AssociationIndex
                for topic in topics:
                    assoc = AssociationIndex(
                        keyword=topic,
                        message_ids=[user_msg.id],
                    )
                    await self.memory.save_association(assoc)
        except Exception as e:
            logger.warning(f"信息提取失败（不影响回复）: {e}")

        return response.content

    async def _get_known_facts(self) -> str:
        """获取已知事实，格式化为文本"""
        facts = await self.memory.get_facts(limit=50)
        if not facts:
            return "（暂无关于她的记录，多和她聊天来了解她吧）"

        lines = []
        for f in facts:
            time_info = f" [{f.event_time}]" if f.event_time else ""
            lines.append(f"- [{f.fact_type}] {f.subject}: {f.content}{time_info}")
        return "\n".join(lines)

    async def _get_recent_context(self) -> str:
        """获取最近的对话上下文"""
        messages = await self.memory.get_messages(
            session_id=self._current_session_id,
            limit=self.settings.memory.max_context_messages,
        )

        if not messages:
            return "（这是新的对话）"

        lines = []
        for m in messages[-20:]:  # 最多带20条
            role_name = self.settings.companion.user_name if m.role == "user" else self.settings.companion.name
            lines.append(f"{role_name}: {m.content}")
        return "\n".join(lines)
