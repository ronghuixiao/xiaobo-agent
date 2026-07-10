"""配置管理模块"""

import os
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field


class OllamaConfig(BaseModel):
    base_url: str = "http://localhost:11434"
    model: str = "qwen2.5:1.5b"
    embedding_model: str = "nomic-embed-text"
    temperature: float = 0.7
    max_tokens: int = 2048


class OpenAIConfig(BaseModel):
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_tokens: int = 2048


class LLMConfig(BaseModel):
    provider: str = "ollama"
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    openai: OpenAIConfig = Field(default_factory=OpenAIConfig)


class MemoryConfig(BaseModel):
    db_path: str = "~/.xiaobo-agent/memory.db"
    max_context_messages: int = 50


class CompanionConfig(BaseModel):
    name: str = "小柏"
    user_name: str = "荣慧"
    daily_report_hour: int = 22
    daily_report_minute: int = 0


class WechatConfig(BaseModel):
    enabled: bool = False
    ilink_token: str = ""
    owner_id: str = ""


class FeishuConfig(BaseModel):
    """飞书配置"""
    enabled: bool = False
    app_id: str = ""
    app_secret: str = ""
    encrypt_key: str = ""
    verification_token: str = ""
    # 你的飞书 open_id（用于接收主动消息）
    owner_id: str = ""
    # webhook 端口
    webhook_port: int = 9000


class Settings(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    companion: CompanionConfig = Field(default_factory=CompanionConfig)
    wechat: WechatConfig = Field(default_factory=WechatConfig)
    feishu: FeishuConfig = Field(default_factory=FeishuConfig)


def load_settings(config_path: Optional[str] = None) -> Settings:
    """加载配置文件，不存在则用默认值"""
    if config_path is None:
        # 默认路径：项目根目录/config/config.yaml
        project_root = Path(__file__).parent.parent
        config_path = project_root / "config" / "config.yaml"

    config_path = Path(config_path)

    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return Settings(**data)

    return Settings()
