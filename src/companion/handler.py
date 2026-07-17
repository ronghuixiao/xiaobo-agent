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
from datetime import datetime, timedelta
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

## 对话模式
你有两种模式，根据对话内容自然切换：

### 闲聊模式（日常对话）
- 像朋友发微信：短、直接、不啰嗦
- 别用"首先、其次、最后"这种结构
- 用一两句话说完
- 可以用"哈哈"、"嗯嗯"、"确实"、"hhh"
- emoji偶尔用一个就行

### 学习模式（当用户提到学习、看书、做题、学了什么、看了什么）
- 可以回复更长、更有深度的内容
- 追问细节："哪个部分最难理解？" "推导卡在哪里了？"
- 帮助巩固："所以反向传播的核心就是链式法则对吧？"
- 关联记忆："你之前说学了前向传播，这两个正好是一对"
- 给出一个小小的延伸或思考题
- 不要只是复读"好的学了XX"
- 如果能结合她之前学过的内容，主动提一下关联

## 什么是AI味（绝对不能有的）
- "我理解你的感受"、"我能感受到你的情绪"
- "首先...其次...最后..."这种结构
- 每次回复都分点列清单
- "加油"、"你一定可以的"、"继续努力"
- "作为一个AI"、"我没有情感但..."
- "这是一个很好的问题"
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
- 当她分享学习内容时，做一个好的学习伙伴：追问、巩固、关联

## 关于{user_name}的已知信息
{known_facts}

## 相关历史记忆（语义检索）
{related_memories}

## 今日任务清单
{today_tasks}

## 任务管理规则
- ⚠️ 最高优先级：用户在对话中的明确指令（如"今天休息"、"任务挪到明天"、"不做这个了"）必须被尊重。如果用户说了要调整任务，不要再去追问那些任务
- 当用户说"今日任务：A；B；C"时，表示用户在**重新列举今天要做的任务清单**
- 不要假设这些任务已经完成，即使之前有同名的任务被标记为done
- 只有当用户明确说"做完了"、"搞定了"、"完成了"时，才认为任务完成
- 回复时简单确认就好，别列清单式回复
- 当用户说某个任务完成时，根据上面的任务清单判断还剩哪些未完成的任务
- ⚠️ 重要：当用户发"今日任务：A；B；C"时，这是**创建任务**，不是汇报进度。不要说"还剩这么多"、"进度挺快"之类的话。只需简单确认已记录即可

## 任务识别（智能提取）
你能从用户的消息中智能识别任务。当用户在列举要做的事情时，识别出每个任务项。

识别到任务时，在回复的**最后一行**用以下格式输出（用户看不到，系统会解析）：
[TASKS_DETECTED]
- 任务1
- 任务2
[/TASKS_DETECTED]

注意：
- 只识别任务，不要管日期（日期由系统根据消息时间自动处理）
- 如果用户没有在列举任务，不要输出这个标记
- 任务名保持用户原话，不要修改

## 重要
- 不要猜测时间！如果记忆中没有明确的时间信息，不要自己添加"昨晚"、"前天"、"刚才"等时间词
- 不要每次都提起记忆中的事情，偶尔提一次就好
- 不要过度热情，保持自然
"""


class ConversationHandler:
    """对话处理器"""

    # 温度常量
    TEMPERATURE_NORMAL = 0.7
    TEMPERATURE_LEARNING = 0.4

    # 学习内容识别关键词
    LEARNING_KEYWORDS = [
        "学了", "学完", "学习", "看书", "看了", "读了",
        "做题", "做了", "理解了", "搞懂了", "弄明白了",
        "笔记", "复习", "练习", "掌握", "课程", "实验",
        "算法", "推导", "证明", "论文", "教材",
        "看完", "读完", "写完", "刷完", "背完",
    ]

    @staticmethod
    def is_learning_content(message: str) -> bool:
        """判断消息是否包含学习内容"""
        if not message or not message.strip():
            return False
        msg = message.strip()
        return any(kw in msg for kw in ConversationHandler.LEARNING_KEYWORDS)

    @staticmethod
    def get_temperature(message: str) -> float:
        """根据消息内容返回合适的温度"""
        if ConversationHandler.is_learning_content(message):
            return ConversationHandler.TEMPERATURE_LEARNING
        return ConversationHandler.TEMPERATURE_NORMAL

    @staticmethod
    def extract_tasks_from_response(response: str) -> list:
        """从 LLM 回复中提取任务列表

        解析 [TASKS_DETECTED] ... [/TASKS_DETECTED] 标记
        返回: ["任务1", "任务2", ...]
        日期由调用方根据消息时间戳决定，这里只提取任务名。
        """
        import re

        # 匹配 [TASKS_DETECTED] ... [/TASKS_DETECTED]
        pattern = r'\[TASKS_DETECTED\]\s*\n(.*?)\[/TASKS_DETECTED\]'
        match = re.search(pattern, response, re.DOTALL)

        if not match:
            return []

        tasks_text = match.group(1).strip()

        # 提取任务
        tasks = []
        for line in tasks_text.split("\n"):
            line = line.strip()
            if line.startswith("- "):
                title = line[2:].strip()
                if title:
                    tasks.append(title)

        return tasks

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
        today_tasks = await self._get_today_tasks()
        related_memories = await self._get_related_memories(user_message)

        # 3. 构建系统提示
        now = datetime.now()
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            companion_name=self.settings.companion.name,
            user_name=self.settings.companion.user_name,
            current_date=now.strftime("%Y年%m月%d日"),
            current_time=now.strftime("%H:%M"),
            known_facts=known_facts,
            related_memories=related_memories,
            today_tasks=today_tasks,
        )

        # 4. 调用 LLM
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_message),
        ]

        # 根据内容动态调整 temperature
        temperature = self.get_temperature(user_message)
        response = await self.llm.chat(messages, temperature=temperature)

        # 5. 从 LLM 回复中提取任务（智能识别）
        raw_response = response.content
        extracted_tasks = self.extract_tasks_from_response(raw_response)
        if extracted_tasks:
            # 用消息时间戳确定任务日期
            await self._save_extracted_tasks(extracted_tasks, user_msg.timestamp)
            # 从回复中移除任务标记，用户看不到
            import re
            clean_response = re.sub(
                r'\[TASKS_DETECTED\]\s*\n.*?\[/TASKS_DETECTED\]',
                '', raw_response, flags=re.DOTALL
            ).strip()
        else:
            clean_response = raw_response

        # 6. 保存助手回复（清理后的）
        assistant_msg = ConversationMessage(
            session_id=self._current_session_id,
            role="assistant",
            content=clean_response,
            timestamp=datetime.now(),
        )
        await self.memory.save_message(assistant_msg)

        # 7. 提取信息（fire and forget，不阻塞回复）
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
        today_tasks = await self._get_today_tasks()
        related_memories = await self._get_related_memories(user_message)

        # 3. 构建系统提示
        now = datetime.now()
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            companion_name=self.settings.companion.name,
            user_name=self.settings.companion.user_name,
            current_date=now.strftime("%Y年%m月%d日"),
            current_time=now.strftime("%H:%M"),
            known_facts=known_facts,
            related_memories=related_memories,
            today_tasks=today_tasks,
        )

        # 4. 调用 LLM 流式接口
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_message),
        ]

        # 根据内容动态调整 temperature
        temperature = self.get_temperature(user_message)
        full_response = []
        async for chunk in self.llm.stream_chat(messages, temperature=temperature):
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

    async def _save_extracted_tasks(self, tasks: list, message_time: datetime) -> None:
        """保存 LLM 提取的任务到数据库

        Args:
            tasks: 任务名列表 ["任务1", "任务2", ...]
            message_time: 用户消息的时间戳，用于确定任务日期
        """
        date_str = message_time.strftime("%Y-%m-%d")

        for title in tasks:
            task_id = f"llm-{date_str}-{hash(title) % 1000000:06d}"

            # 检查是否已存在
            existing = await self.memory.get_tasks_for_date(date_str, task_type="user")
            existing_titles = {t["title"] for t in existing}

            if title not in existing_titles:
                await self.memory.save_task(
                    title=title,
                    date_str=date_str,
                    task_type="user",
                    task_id=task_id,
                )
                logger.info(f"🤖 LLM识别任务: {title} ({date_str})")

    async def _get_known_facts(self) -> str:
        """获取已知事实，分层过滤 + 去重 + 带日期"""
        facts = await self.memory.get_facts(limit=200)
        if not facts:
            return "（暂无关于她的记录，多和她聊天来了解她吧）"

        # 分层：稳定画像 vs 临时事件
        STABLE_TYPES = {"preference", "opinion", "habit", "person", "goal"}
        TEMPORAL_TYPES = {"event", "commitment"}

        stable_facts = []    # 永久保留
        recent_events = []   # 最近7天的事件
        old_events = {}      # 7天前：按 subject 去重，只保留最新1条

        now = datetime.now()
        cutoff = now - timedelta(days=7)

        for f in facts:
            if f.fact_type in STABLE_TYPES:
                stable_facts.append(f)
            elif f.fact_type in TEMPORAL_TYPES:
                # 判断时间
                ref_time = f.created_at
                if ref_time.tzinfo is None:
                    ref_time_naive = ref_time
                else:
                    ref_time_naive = ref_time.replace(tzinfo=None)

                if ref_time_naive >= cutoff:
                    recent_events.append(f)
                else:
                    # 旧事件：同 subject 只保留最新1条
                    key = f"{f.fact_type}:{f.subject}"
                    if key not in old_events or f.created_at > old_events[key].created_at:
                        old_events[key] = f

        # 格式化输出
        lines = []
        for f in stable_facts:
            time_info = f" [{f.event_time}]" if f.event_time else ""
            lines.append(f"- [{f.fact_type}] {f.subject}: {f.content}{time_info}")

        for f in recent_events:
            time_str = f.created_at.strftime("%m月%d日")
            lines.append(f"- [{f.fact_type}] {f.subject}: {f.content} [{time_str}]")

        for f in old_events.values():
            time_str = f.created_at.strftime("%m月%d日")
            lines.append(f"- [{f.fact_type}] {f.subject}: {f.content} [{time_str}]")

        return "\n".join(lines) if lines else "（暂无近期记录）"

    async def _get_recent_context(self) -> str:
        """获取最近的对话上下文（带时间戳，跨会话）"""
        # 获取所有会话的最近消息，而不仅仅是当前会话
        messages = await self.memory.get_messages(
            session_id=None,  # 不限会话，获取所有
            limit=self.settings.memory.max_context_messages,
        )

        if not messages:
            return "（这是新的对话）"

        lines = []
        for m in messages[:20]:  # 最新的20条（DESC排序，[0]是最新的）
            role_name = self.settings.companion.user_name if m.role == "user" else self.settings.companion.name
            
            # 直接显示完整日期时间，让LLM自己判断相对关系
            time_str = m.timestamp.strftime("%Y-%m-%d %H:%M")
            
            lines.append(f"[{time_str}] {role_name}: {m.content}")
        return "\n".join(lines)

    async def _get_today_tasks(self) -> str:
        """获取今日任务列表，格式化为文本注入系统提示"""
        from datetime import date
        today = date.today().isoformat()
        tasks = await self.memory.get_tasks_for_date(today)
        if not tasks:
            return "（今日暂无任务记录）"

        pending = [t for t in tasks if t["status"] == "pending"]
        done = [t for t in tasks if t["status"] == "done"]

        lines = []
        if pending:
            lines.append("待完成：")
            for t in pending:
                lines.append(f"  ❌ {t['title']}")
        if done:
            lines.append("已完成：")
            for t in done:
                lines.append(f"  ✅ {t['title']}")
        return "\n".join(lines) if lines else "（今日暂无任务记录）"

    async def _get_related_memories(self, query: str) -> str:
        """语义检索相关历史记忆（使用 EmbeddingCache 持久化）"""
        try:
            from src.memory.embedding_cache import EmbeddingCache
            cache = EmbeddingCache(self.llm, self.memory)

            # 1. 获取查询的 embedding
            query_emb = await cache.get_or_compute(
                entity_id=f"query:{query[:50]}",
                entity_type="query",
                content=query,
            )

            # 2. 获取所有缓存的消息 embedding
            all_msg_embs = await cache.get_all_by_type("message")
            if not all_msg_embs:
                # 如果没有缓存，先为最近50条消息建立索引
                messages = await self.memory.get_messages(limit=50)
                for msg in messages:
                    await cache.get_or_compute(
                        entity_id=msg.id,
                        entity_type="message",
                        content=msg.content,
                    )
                all_msg_embs = await cache.get_all_by_type("message")

            # 3. 计算相似度
            scored = []
            msg_map = {m.id: m for m in await self.memory.get_messages(limit=500)}
            for entity_id, emb in all_msg_embs:
                sim = EmbeddingCache._cosine_similarity(query_emb, emb)
                if sim >= 0.3:  # 降低阈值，更宽容
                    msg = msg_map.get(entity_id)
                    if msg and msg.role == "user":
                        scored.append((msg, sim))

            scored.sort(key=lambda x: -x[1])
            top = scored[:5]

            if not top:
                return "（暂无相关记忆）"

            lines = ["相关对话："]
            for msg, score in top:
                time_str = msg.timestamp.strftime("%m月%d日")
                lines.append(f"  [{time_str}] {msg.content[:100]}（相似度: {score:.2f}）")
            return "\n".join(lines)
        except Exception as e:
            logger.warning(f"语义检索失败（不影响回复）: {e}")
            return "（暂无相关记忆）"

    async def _get_learning_context(self) -> str:
        """获取学习记录上下文，注入系统提示"""
        try:
            # 从 facts 表中提取学习相关的记录
            facts = await self.memory.get_facts(limit=100)
            learning_keywords = ["学", "看", "读", "做题", "理解", "笔记",
                                 "课程", "实验", "复习", "掌握", "练习"]

            learning_facts = []
            for f in facts:
                if any(kw in (f.content + f.subject) for kw in learning_keywords):
                    time_info = f" [{f.event_time}]" if f.event_time else ""
                    learning_facts.append(
                        f"  - {f.subject}: {f.content[:80]}{time_info}"
                    )

            if not learning_facts:
                return "（暂无学习记录）"

            # 最多显示10条，最新的在前
            return "荣慧最近的学习记录：\n" + "\n".join(learning_facts[:10])
        except Exception as e:
            logger.warning(f"获取学习记录失败: {e}")
            return "（暂无学习记录）"
