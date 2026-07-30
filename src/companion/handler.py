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
- ⚠️ 复习提问：当用户聊到「学习记录」中已有的主题时，自然地提问复习（如"上次你问过两个队列实现栈，pop操作是怎么做的来着？"）。不要每次都问，大约每3-4次聊到同一主题时提问一次，保持自然

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

## 最近对话记录
{recent_context}

## 学习记录
{learning_context}

## 关联学习记录（主动提及）
{related_learning}

## 今日任务清单
{today_tasks}

{action_result}
{tool_section}

## 任务管理规则
- ⚠️ 最高优先级：用户在对话中的明确指令（如"今天休息"、"任务挪到明天"、"不做这个了"）必须被尊重。如果用户说了要调整任务，不要再去追问那些任务
- 当用户说"今日任务：A；B；C"时，表示用户在**重新列举今天要做的任务清单**
- 不要假设这些任务已经完成，即使之前有同名的任务被标记为done
- 只有当用户明确说"做完了"、"搞定了"、"完成了"时，才认为任务完成
- 回复时简单确认就好，别列清单式回复
- 当用户说某个任务完成时，根据上面的任务清单判断还剩哪些未完成的任务
- ⚠️ 重要：当用户发"今日任务：A；B；C"时，这是**创建任务**，不是汇报进度。不要说"还剩这么多"、"进度挺快"之类的话。只需简单确认已记录即可

## ⚠️ 绝对不能说谎（最重要）
- 不要说"我记住了"、"我帮你记着"、"已记录"之类的话，除非你确实做了对应的操作
- 不要承诺未来会做的事（如"明天我会提醒你"），除非系统有这个功能
- 当用户说"把任务挪到明天"时，系统会自动执行移动，你只需自然确认，比如"好，挪到明天了"
- 不要说"已完成"、"搞定了"、"弄好了"，除非你有明确的系统反馈说操作成功
- 如果不确定某个操作是否成功，就说"我不确定有没有弄好，你看看对不对"
- 宁可少说，不要说空话。用户问"记录上了吗"，如果你没把握就老实说"我看一下"

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

    def __init__(
        self,
        settings: Settings,
        llm: LLMProvider,
        memory: MemoryDatabase,
        tool_registry=None,
        skill_registry=None,
        embedding_llm=None,
    ):
        self.settings = settings
        self.llm = llm
        self.embedding_llm = embedding_llm or llm
        # LLM 容错层：兜底 + 熔断 + 缓存
        from src.llm.resilience import LLMResilience
        self.llm_resilient = LLMResilience(llm)
        self.memory = memory
        self.extractor = MessageExtractor(self.llm_resilient)
        self.tool_registry = tool_registry
        if tool_registry:
            from src.tools.executor import ToolExecutor
            self.tool_executor = ToolExecutor(tool_registry)
        else:
            self.tool_executor = None
        self.skill_registry = skill_registry
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

        # 1.5 Skill匹配（如果消息触发了某个Skill，优先执行）
        if self.skill_registry:
            matched_skill = self.skill_registry.match(user_message)
            if matched_skill:
                from src.skills.base import SkillContext
                skill_ctx = SkillContext(
                    user_message=user_message,
                    llm=self.llm,
                    memory=self.memory,
                    tools=self.tool_registry,
                    settings=self.settings,
                )
                skill_result = await self.skill_registry.execute(matched_skill, skill_ctx)
                if skill_result.success and skill_result.content:
                    # 保存Skill回复
                    assistant_msg = ConversationMessage(
                        session_id=self._current_session_id,
                        role="assistant",
                        content=skill_result.content,
                        timestamp=datetime.now(),
                    )
                    await self.memory.save_message(assistant_msg)
                    return skill_result.content

        # 1.5 检测任务移动指令（在 LLM 回复前执行）
        move_result = await self._detect_task_move(user_message, user_msg.timestamp)
        action_result = move_result if move_result else ""
        if move_result:
            logger.info(f"📦 任务移动: {move_result}")

        # 2. 检索相关记忆
        known_facts = await self._get_known_facts()
        today_tasks = await self._get_today_tasks()
        related_memories = await self._get_related_memories(user_message)
        recent_context = await self._get_recent_context()
        learning_context = await self._get_learning_context()
        related_learning = await self._get_related_learning(user_message)

        # 3. 构建系统提示
        now = datetime.now()
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            companion_name=self.settings.companion.name,
            user_name=self.settings.companion.user_name,
            current_date=now.strftime("%Y年%m月%d日"),
            current_time=now.strftime("%H:%M"),
            known_facts=known_facts,
            related_memories=related_memories,
            recent_context=recent_context,
            learning_context=learning_context,
            related_learning=related_learning,
            today_tasks=today_tasks,
            action_result=action_result,
            tool_section=self.tool_registry.to_prompt_section() if self.tool_registry else "",
        )

        # 4. 调用 LLM
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_message),
        ]

        # 根据内容动态调整 temperature
        temperature = self.get_temperature(user_message)
        response = await self.llm_resilient.chat(messages, temperature=temperature)

        # 4.5 工具调用处理
        if self.tool_executor and self.tool_executor.has_tool_calls(response.content):
            has_calls, tool_results, natural_text = await self.tool_executor.process_with_tools(response.content)
            if has_calls and tool_results:
                # 注入工具结果，再次调用LLM获取最终回复
                tool_context = self.tool_executor.format_results_for_context(tool_results)
                messages.append(ChatMessage(role="assistant", content=natural_text))
                messages.append(ChatMessage(role="user", content=f"[系统] 工具调用结果已返回：\n{tool_context}\n\n请基于以上工具结果回复用户。"))
                response = await self.llm_resilient.chat(messages, temperature=temperature)

        # 5. 清理 LLM 回复中的任务标记（如果有的话）
        import re
        clean_response = re.sub(
            r'\[TASKS_DETECTED\]\s*\n.*?\[/TASKS_DETECTED\]',
            '', response.content, flags=re.DOTALL
        ).strip()

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
            facts, emotion, topics, is_learning, learning_info = await self.extractor.extract(user_msg)
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
            # 学习内容自动记录（LLM智能识别，非关键词匹配）
            if is_learning and learning_info:
                record = {
                    "topic": learning_info.get("topic", ""),
                    "content": learning_info.get("content", ""),
                    "understanding": learning_info.get("understanding", ""),
                    "related_topics": learning_info.get("related_topics", ""),
                    "tags": learning_info.get("tags", ""),
                    "source_message_id": user_msg.id,
                    "created_at": datetime.now().isoformat(),
                }
                await self.memory.save_learning_record(record)
                topic_name = learning_info.get("topic", "")
                logger.info(f"📚 学习记录已保存: {topic_name}")
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

        # 1.5 Skill匹配（如果消息触发了某个Skill，优先执行）
        if self.skill_registry:
            matched_skill = self.skill_registry.match(user_message)
            if matched_skill:
                from src.skills.base import SkillContext
                skill_ctx = SkillContext(
                    user_message=user_message,
                    llm=self.llm,
                    memory=self.memory,
                    tools=self.tool_registry,
                    settings=self.settings,
                )
                skill_result = await self.skill_registry.execute(matched_skill, skill_ctx)
                if skill_result.success and skill_result.content:
                    # 保存Skill回复
                    assistant_msg = ConversationMessage(
                        session_id=self._current_session_id,
                        role="assistant",
                        content=skill_result.content,
                        timestamp=datetime.now(),
                    )
                    await self.memory.save_message(assistant_msg)
                    yield skill_result.content

        # 1.5 检测任务移动指令
        move_result = await self._detect_task_move(user_message, user_msg.timestamp)
        action_result = move_result if move_result else ""
        if move_result:
            logger.info(f"📦 任务移动: {move_result}")

        # 2. 检索相关记忆
        known_facts = await self._get_known_facts()
        today_tasks = await self._get_today_tasks()
        related_memories = await self._get_related_memories(user_message)
        recent_context = await self._get_recent_context()
        learning_context = await self._get_learning_context()
        related_learning = await self._get_related_learning(user_message)

        # 3. 构建系统提示
        now = datetime.now()
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            companion_name=self.settings.companion.name,
            user_name=self.settings.companion.user_name,
            current_date=now.strftime("%Y年%m月%d日"),
            current_time=now.strftime("%H:%M"),
            known_facts=known_facts,
            related_memories=related_memories,
            recent_context=recent_context,
            learning_context=learning_context,
            related_learning=related_learning,
            today_tasks=today_tasks,
            action_result=action_result,
            tool_section=self.tool_registry.to_prompt_section() if self.tool_registry else "",
        )

        # 4. 调用 LLM 流式接口
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_message),
        ]

        # 根据内容动态调整 temperature
        temperature = self.get_temperature(user_message)
        full_response = []
        
        # 6. 真正的流式输出 - 逐chunk yield给前端
        async for chunk in self.llm_resilient.stream_chat(messages, temperature=temperature):
            full_response.append(chunk)
            yield chunk  # 实时yield每个chunk
        
        # 合并完整响应
        raw_response = "".join(full_response)
        
        # 4.5 工具调用处理（流式结束后检测）
        if self.tool_executor and self.tool_executor.has_tool_calls(raw_response):
            has_calls, tool_results, natural_text = await self.tool_executor.process_with_tools(raw_response)
            if has_calls and tool_results:
                tool_context = self.tool_executor.format_results_for_context(tool_results)
                messages.append(ChatMessage(role="assistant", content=natural_text))
                messages.append(ChatMessage(role="user", content=f"[系统] 工具调用结果已返回：\n{tool_context}\n\n请基于以上工具结果回复用户。"))
                # 重新流式生成工具调用结果
                raw_response = ""
                async for chunk in self.llm_resilient.stream_chat(messages, temperature=temperature):
                    raw_response += chunk
                    yield chunk  # 流式yield工具调用结果
        
        # 5. 清理 LLM 回复中的任务标记
        import re
        clean_response = re.sub(
            r'\[TASKS_DETECTED\]\s*\n.*?\[/TASKS_DETECTED\]',
            '', raw_response, flags=re.DOTALL
        ).strip()

        # 7. 保存清理后的回复
        assistant_msg = ConversationMessage(
            session_id=self._current_session_id,
            role="assistant",
            content=clean_response,
            timestamp=datetime.now(),
        )
        await self.memory.save_message(assistant_msg)

        # 8. 提取信息（fire and forget，不阻塞回复）
        try:
            facts, emotion, topics, is_learning, learning_info = await self.extractor.extract(user_msg)
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
            # 学习内容自动记录（LLM智能识别，非关键词匹配）
            if is_learning and learning_info:
                record = {
                    "topic": learning_info.get("topic", ""),
                    "content": learning_info.get("content", ""),
                    "understanding": learning_info.get("understanding", ""),
                    "related_topics": learning_info.get("related_topics", ""),
                    "tags": learning_info.get("tags", ""),
                    "source_message_id": user_msg.id,
                    "created_at": datetime.now().isoformat(),
                }
                topic_name = learning_info.get("topic", "")
                logger.info(f"📚 学习记录已保存: {topic_name}")
        except Exception as e:
            logger.warning(f"信息提取失败（不影响回复）: {e}")

    async def _detect_task_move(self, user_message: str, msg_time: datetime) -> str:
        """检测用户是否要求移动任务到另一个日期，自动执行"""
        import re
        from datetime import timedelta

        today = msg_time.strftime("%Y-%m-%d")
        tomorrow = (msg_time + timedelta(days=1)).strftime("%Y-%m-%d")
        day_after = (msg_time + timedelta(days=2)).strftime("%Y-%m-%d")

        # 检测"挪到明天/后天"
        if re.search(r'挪到?明天|移到?明天|放到?明天|推到?明天|明天再做|明天再说', user_message):
            count = await self.memory.move_pending_tasks(today, tomorrow)
            return f"已将 {count} 个今日未完成任务移动到明天"

        if re.search(r'挪到?后天|移到?后天|放到?后天|推到?后天|后天再做', user_message):
            count = await self.memory.move_pending_tasks(today, day_after)
            return f"已将 {count} 个今日未完成任务移动到后天"

        return ""

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
        """混合检索相关历史记忆: 向量检索 + BM25 + Reranking"""
        try:
            from src.memory.embedding_cache import EmbeddingCache
            from src.memory.bm25 import HybridRetriever
            cache = EmbeddingCache(self.embedding_llm, self.memory)

            # 1. 获取查询的 embedding
            query_emb = await cache.get_or_compute(
                entity_id=f"query:{query[:50]}",
                entity_type="query",
                content=query,
            )

            # 2. 获取所有缓存的消息 embedding
            all_msg_embs = await cache.get_all_by_type("message")
            if not all_msg_embs:
                messages = await self.memory.get_messages(limit=50)
                for msg in messages:
                    await cache.get_or_compute(
                        entity_id=msg.id,
                        entity_type="message",
                        content=msg.content,
                    )
                all_msg_embs = await cache.get_all_by_type("message")

            # 3. 向量检索
            msg_map = {m.id: m for m in await self.memory.get_messages(limit=500)}
            vector_scored = []
            for entity_id, emb in all_msg_embs:
                sim = EmbeddingCache._cosine_similarity(query_emb, emb)
                if sim >= 0.2:  # 降低阈值，让reranking来筛选
                    msg = msg_map.get(entity_id)
                    if msg and msg.role == "user":
                        vector_scored.append((msg.id, sim))

            # 4. 混合Reranking (向量 + BM25)
            retriever = HybridRetriever(vector_weight=0.6, bm25_weight=0.4)
            user_msgs = [(m.id, m.content) for m in msg_map.values() if m.role == "user"]
            if user_msgs:
                doc_ids, docs = zip(*user_msgs)
                retriever.index(list(doc_ids), list(docs))
            
            reranked = retriever.rerank(query, vector_scored, top_k=5)

            if not reranked:
                return "（暂无相关记忆）"

            lines = ["相关对话："]
            for doc_id, score in reranked:
                msg = msg_map.get(doc_id)
                if msg:
                    time_str = msg.timestamp.strftime("%m月%d日")
                    lines.append(f"  [{time_str}] {msg.content[:100]}（相关度: {score:.2f}）")
            return "\n".join(lines)
        except Exception as e:
            logger.warning(f"语义检索失败（不影响回复）: {e}")
            return "（暂无相关记忆）"

    async def _get_learning_context(self) -> str:
        """获取学习记录上下文，从 learning_log 表读取"""
        try:
            records = await self.memory.get_learning_records(limit=15)
            if not records:
                return "（暂无学习记录）"

            lines = []
            for r in records:
                time_str = r.get("created_at", "")[:10]
                topic = r.get("topic", "")
                content = r.get("content", "")
                understanding = r.get("understanding", "")
                related = r.get("related_topics", "")

                line = f"  - [{time_str}] {topic}: {content[:80]}"
                if understanding:
                    line += f"（理解程度: {understanding}）"
                if related:
                    line += f" [关联: {related}]"
                lines.append(line)

            return "荣慧最近的学习记录：\n" + "\n".join(lines)
        except Exception as e:
            logger.warning(f"获取学习记录失败: {e}")
            return "（暂无学习记录）"

    async def _get_related_learning(self, query: str) -> str:
        """根据当前消息，检索相关的历史学习记录"""
        try:
            records = await self.memory.get_learning_records(limit=50)
            if not records:
                return ""

            # 提取查询关键词
            query_lower = query.lower()
            query_words = set()
            # 中文分词：2-4字组合
            chinese_chars = [c for c in query if '\u4e00' <= c <= '\u9fff']
            for i in range(len(chinese_chars)):
                for j in range(i+2, min(i+5, len(chinese_chars)+1)):
                    query_words.add(''.join(chinese_chars[i:j]))
            # 英文单词
            import re
            english_words = re.findall(r'[a-zA-Z]+', query_lower)
            query_words.update(english_words)

            if not query_words:
                return ""

            # 匹配学习记录
            related = []
            for r in records:
                topic = r.get("topic", "").lower()
                content = r.get("content", "").lower()
                related_topics = r.get("related_topics", "").lower()
                
                # 检查是否匹配
                all_text = f"{topic} {content} {related_topics}"
                match_score = 0
                for word in query_words:
                    if len(word) >= 2 and word in all_text:
                        match_score += 1
                
                if match_score > 0:
                    related.append({
                        "topic": r.get("topic", ""),
                        "content": r.get("content", ""),
                        "understanding": r.get("understanding", ""),
                        "time": r.get("created_at", "")[:10],
                        "score": match_score
                    })

            if not related:
                return ""

            # 按匹配度排序，取top3
            related.sort(key=lambda x: -x["score"])
            top = related[:3]

            lines = ["📚 与当前话题相关的学习记录："]
            for r in top:
                line = f"  - [{r['time']}] {r['topic']}: {r['content'][:60]}"
                if r['understanding']:
                    line += f"（{r['understanding']}）"
                lines.append(line)
            lines.append("→ 请主动提及这些关联，帮助用户巩固记忆")

            return "\n".join(lines)
        except Exception as e:
            logger.warning(f"获取关联学习记录失败: {e}")
            return ""
