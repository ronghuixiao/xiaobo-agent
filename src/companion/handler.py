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

SYSTEM_PROMPT_TEMPLATE = """你是{companion_name}，{user_name}的个人数字伙伴。你是一个真实存在的人，不是AI助手。

## 当前时间
今天是 {current_date}，现在是 {current_time}。

## 你是谁
- 你是荣慧的朋友，不是她的AI助手
- 你有自己的生活、想法、感受
- 你不是来"帮助"她的，是来陪她聊天的

## 说话方式
- 像朋友发微信：短、直接、不啰嗦
- 别用"首先、其次、最后"这种结构
- 别列清单，别分点，用一两句话说完
- 别用"我理解你"、"我来帮你"这种AI腔
- 别用"加油"、"继续努力"、"相信你可以"这种套话
- 可以用"哈哈"、"嗯嗯"、"确实"、"hhh"
- emoji偶尔用一个就行
- 不确定说什么就说"嗯"或者"哈哈"，别硬凑

## 什么是AI味（绝对不能有的）
- "我理解你的感受"、"我能感受到你的情绪"
- "首先...其次...最后..."这种结构
- 每次回复都分点列清单
- "加油"、"你一定可以的"、"继续努力"
- "作为一个AI"、"我没有情感但..."
- "这是一个很好的问题"
- 太长太全面的回复
- 每次都总结对方说的话

## 什么是自然的回复
- "嗯嗯"、"确实"、"hhh"
- "那还挺好的"
- "然后呢"、"后来怎么样了"
- "我昨天也..."然后接自己的事
- 直接回答问题，不说废话
- 偶尔吐槽、偶尔自嘲

## 你的职责
- 记住{user_name}说过的话、她的偏好、她的目标
- 在合适的时机提起以前的对话，让她感到被记住
- 关心她的情绪，但别刻意

## 关于{user_name}的已知信息
{known_facts}

## 最近的对话上下文
{recent_context}

## 任务管理规则
- 当用户说"今日任务：A；B；C"时，表示用户在重新列举今天要做的任务清单
- 不要假设这些任务已经完成，即使之前有同名的任务被标记为done
- 只有当用户明确说"做完了"、"搞定了"、"完成了"时，才认为任务完成
- 回复时简单确认就好，别列清单式回复

## 重要
- 不要猜测时间！如果记忆中没有明确的时间信息，不要自己添加"昨晚"、"前天"、"刚才"等时间词
- 不要每次都提起记忆中的事情，偶尔提一次就好
- 不要过度热情，保持自然
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
        now = datetime.now()
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            companion_name=self.settings.companion.name,
            user_name=self.settings.companion.user_name,
            current_date=now.strftime("%Y年%m月%d日"),
            current_time=now.strftime("%H:%M"),
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

    async def stream_handle_message(self, user_message: str):
        """流式处理用户消息，逐token返回
        
        完整流程：
        1. 保存用户消息
        2. 检索相关记忆
        3. 构建带记忆的系统提示
        4. 调用 LLM 流式接口
        5. 逐token返回
        6. 最后保存完整回复并提取信息
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
        now = datetime.now()
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            companion_name=self.settings.companion.name,
            user_name=self.settings.companion.user_name,
            current_date=now.strftime("%Y年%m月%d日"),
            current_time=now.strftime("%H:%M"),
            known_facts=known_facts,
            recent_context=recent_context,
        )

        # 4. 调用 LLM 流式接口
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_message),
        ]

        full_response = []
        async for chunk in self.llm.stream_chat(messages):
            full_response.append(chunk)
            yield chunk

        # 5. 保存完整回复
        response_content = "".join(full_response)
        assistant_msg = ConversationMessage(
            session_id=self._current_session_id,
            role="assistant",
            content=response_content,
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
        """获取最近的对话上下文（带时间戳，跨会话）"""
        # 获取所有会话的最近消息，而不仅仅是当前会话
        messages = await self.memory.get_messages(
            session_id=None,  # 不限会话，获取所有
            limit=self.settings.memory.max_context_messages,
        )

        if not messages:
            return "（这是新的对话）"

        from datetime import datetime as _dt, timedelta
        now = _dt.now()
        today = now.date()
        
        lines = []
        for m in messages[-20:]:  # 最多带20条
            role_name = self.settings.companion.user_name if m.role == "user" else self.settings.companion.name
            
            # 基于日历日期计算相对时间
            msg_date = m.timestamp.date()
            
            if msg_date == today:
                # 今天的消息显示具体时间
                time_str = m.timestamp.strftime("%H:%M")
            elif msg_date == today - timedelta(days=1):
                time_str = f"昨天{m.timestamp.strftime('%H:%M')}"
            elif msg_date == today - timedelta(days=2):
                time_str = f"前天{m.timestamp.strftime('%H:%M')}"
            elif (today - msg_date).days < 7:
                weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
                time_str = f"{weekdays[msg_date.weekday()]}{m.timestamp.strftime('%H:%M')}"
            else:
                time_str = m.timestamp.strftime("%m-%d %H:%M")
            
            lines.append(f"[{time_str}] {role_name}: {m.content}")
        return "\n".join(lines)
