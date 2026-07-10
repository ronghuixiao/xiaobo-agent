"""记忆系统基类和数据模型

分层记忆架构：
- Layer 0: 原始对话存档（全量，带时间戳）
- Layer 1: 提取的事实和模式（结构化）
- Layer 2: 情绪和状态时间线（情感维度）
- Layer 3: 关联索引（关键词 → 对话映射）
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid


class EmotionType(str, Enum):
    """情绪类型"""
    HAPPY = "happy"
    SAD = "sad"
    ANXIOUS = "anxious"
    EXCITED = "excited"
    CALM = "calm"
    FRUSTRATED = "frustrated"
    TIRED = "tired"
    NEUTRAL = "neutral"


class FactType(str, Enum):
    """事实类型"""
    PERSON = "person"          # 人物关系
    PREFERENCE = "preference"  # 偏好
    ABILITY = "ability"        # 能力
    GOAL = "goal"              # 目标
    HABIT = "habit"            # 习惯
    EVENT = "event"            # 事件
    COMMITMENT = "commitment"  # 承诺/计划
    OPINION = "opinion"        # 观点


@dataclass
class ConversationMessage:
    """Layer 0: 原始对话消息"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    role: str = ""  # "user" or "assistant"
    content: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    emotion: Optional[str] = None
    topics: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractedFact:
    """Layer 1: 提取的事实"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    fact_type: str = ""  # FactType value
    subject: str = ""    # 关于什么
    content: str = ""    # 事实内容
    confidence: float = 1.0
    source_message_id: str = ""
    event_time: Optional[str] = None  # 事件发生时间（绝对时间，如"2026-07-07晚上"）
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    is_active: bool = True  # 是否仍然有效


@dataclass
class EmotionRecord:
    """Layer 2: 情绪记录"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    emotion: str = ""  # EmotionType value
    intensity: float = 0.5  # 0-1
    context: str = ""   # 触发情绪的上下文
    source_message_id: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class AssociationIndex:
    """Layer 3: 关联索引"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    keyword: str = ""
    message_ids: List[str] = field(default_factory=list)
    fact_ids: List[str] = field(default_factory=list)
    last_updated: datetime = field(default_factory=datetime.now)
