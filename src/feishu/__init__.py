"""飞书连接层 - 飞书自建应用机器人

支持：
- WebSocket 长连接接收消息
- 主动发送消息（文本/富文本）
- 群聊 @机器人 触发
"""
import asyncio
import hashlib
import hmac
import json
import logging
import time
import threading
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

try:
    import aiohttp
    from aiohttp import web
    AIOHTTP_AVAILABLE = True
except ImportError:
    aiohttp = None
    web = None
    AIOHTTP_AVAILABLE = False

# 飞书 API 常量
FEISHU_BASE_URL = "https://open.feishu.cn/open-apis"


@dataclass
class FeishuConfig:
    """飞书配置"""
    app_id: str = ""
    app_secret: str = ""
    encrypt_key: str = ""
    verification_token: str = ""
    # webhook 端口（用于接收事件回调）
    webhook_port: int = 9000
    webhook_path: str = "/feishu/webhook"


class FeishuMessage:
    """飞书消息"""
    def __init__(
        self,
        msg_id: str = "",
        sender_id: str = "",
        sender_name: str = "",
        content: str = "",
        chat_id: str = "",
        chat_type: str = "p2p",  # p2p or group
        msg_type: str = "text",
    ):
        self.msg_id = msg_id
        self.sender_id = sender_id
        self.sender_name = sender_name
        self.content = content
        self.chat_id = chat_id
        self.chat_type = chat_type
        self.msg_type = msg_type


class FeishuConnection:
    """飞书连接管理器

    支持两种接收消息模式：
    1. Webhook 模式（推荐）：飞书主动推送事件到你的服务器
    2. WebSocket 模式：长连接（需要 lark_oapi SDK）

    发送消息使用飞书开放 API。
    """

    def __init__(self, config: Optional[FeishuConfig] = None):
        if not AIOHTTP_AVAILABLE:
            raise ImportError("需要安装 aiohttp: pip install aiohttp")
        self.config = config or FeishuConfig()
        self._session: Optional[aiohttp.ClientSession] = None
        self._running = False
        self._tenant_access_token: str = ""
        self._token_expires_at: float = 0
        self._on_message: Optional[Callable] = None
        self._chat_sessions: Dict[str, str] = {}  # chat_id -> session_id

    # ==================== Token 管理 ====================

    async def _get_tenant_access_token(self) -> str:
        """获取 tenant_access_token"""
        if self._tenant_access_token and time.time() < self._token_expires_at:
            return self._tenant_access_token

        if not self._session:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            )

        payload = {
            "app_id": self.config.app_id,
            "app_secret": self.config.app_secret,
        }

        try:
            async with self._session.post(
                f"{FEISHU_BASE_URL}/auth/v3/tenant_access_token/internal",
                json=payload,
            ) as resp:
                data = await resp.json()
                if data.get("code") == 0:
                    self._tenant_access_token = data["tenant_access_token"]
                    # 提前 5 分钟刷新
                    self._token_expires_at = time.time() + data.get("expire", 7200) - 300
                    logger.info("飞书 tenant_access_token 获取成功")
                    return self._tenant_access_token
                else:
                    logger.error(f"获取 token 失败: {data}")
                    return ""
        except Exception as e:
            logger.error(f"获取 token 异常: {e}")
            return ""

    def _auth_headers(self, token: str = "") -> Dict[str, str]:
        """构造认证请求头"""
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    # ==================== 连接管理 ====================

    async def start(self):
        """启动连接"""
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30)
        )
        self._running = True
        # 先获取 token
        await self._get_tenant_access_token()
        logger.info("飞书连接已启动")

    async def stop(self):
        """停止连接"""
        self._running = False
        if self._session:
            await self._session.close()
        logger.info("飞书连接已关闭")

    # ==================== Webhook 接收消息 ====================

    async def start_webhook_server(self, host: str = "0.0.0.0"):
        """启动 Webhook 服务器接收飞书事件回调"""
        if not web:
            raise ImportError("需要安装 aiohttp")

        app = web.Application()
        app.router.add_post(self.config.webhook_path, self._handle_webhook)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host, self.config.webhook_port)
        await site.start()
        logger.info(f"飞书 Webhook 服务器启动: {host}:{self.config.webhook_port}{self.config.webhook_path}")

    async def _handle_webhook(self, request: web.Request) -> web.Response:
        """处理飞书 Webhook 回调"""
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)

        # URL 验证（飞书首次配置时会发送）
        if body.get("type") == "url_verification":
            return web.json_response({"challenge": body.get("challenge", "")})

        # 验证 token
        token = body.get("token", "")
        if self.config.verification_token and token != self.config.verification_token:
            logger.warning(f"飞书 Webhook token 验证失败: {token}")
            return web.json_response({"error": "invalid token"}, status=403)

        # 处理事件
        event = body.get("event", {})
        event_type = body.get("header", {}).get("event_type", "")

        if event_type == "im.message.receive_v1":
            await self._on_receive_message(event)

        return web.json_response({"code": 0})

    async def _on_receive_message(self, event: Dict):
        """处理接收到的消息"""
        message = event.get("message", {})
        sender = event.get("sender", {}).get("sender_id", {})

        msg_type = message.get("message_type", "")
        chat_id = message.get("chat_id", "")
        chat_type = message.get("chat_type", "p2p")
        msg_id = message.get("message_id", "")

        # 只处理文本消息
        if msg_type != "text":
            return

        # 解析文本内容
        content = message.get("content", "{}")
        try:
            content_obj = json.loads(content)
            text = content_obj.get("text", "").strip()
        except (json.JSONDecodeError, TypeError):
            text = content

        if not text:
            return

        # 去掉 @机器人 的部分
        mentions = message.get("mentions", [])
        for mention in mentions:
            key = mention.get("key", "")
            if key:
                text = text.replace(key, "").strip()

        if not text:
            return

        feishu_msg = FeishuMessage(
            msg_id=msg_id,
            sender_id=sender.get("open_id", ""),
            sender_name=event.get("sender", {}).get("sender_id", {}).get("open_id", ""),
            content=text,
            chat_id=chat_id,
            chat_type=chat_type,
            msg_type=msg_type,
        )

        logger.info(f"收到飞书消息: [{chat_type}] {text[:50]}")

        if self._on_message:
            await self._on_message(feishu_msg)

    def on_message(self, callback: Callable):
        """注册消息回调"""
        self._on_message = callback

    # ==================== 发送消息 ====================

    async def send_text(self, chat_id: str, text: str) -> bool:
        """发送文本消息到指定会话

        Args:
            chat_id: 会话 ID（open_id 或 chat_id）
            text: 消息文本
        """
        token = await self._get_tenant_access_token()
        if not token:
            return False

        payload = {
            "receive_id": chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        }

        try:
            async with self._session.post(
                f"{FEISHU_BASE_URL}/im/v1/messages?receive_id_type=open_id",
                json=payload,
                headers=self._auth_headers(token),
            ) as resp:
                data = await resp.json()
                if data.get("code") == 0:
                    logger.info(f"飞书消息发送成功: chat_id={chat_id}")
                    return True
                else:
                    logger.warning(f"飞书消息发送失败: {data}")
                    return False
        except Exception as e:
            logger.error(f"飞书消息发送异常: {e}")
            return False

    async def send_rich_text(self, chat_id: str, title: str, content_lines: List[List[Dict]]) -> bool:
        """发送富文本消息

        Args:
            chat_id: 会话 ID
            title: 消息标题
            content_lines: 富文本内容（嵌套数组格式）
        """
        token = await self._get_tenant_access_token()
        if not token:
            return False

        payload = {
            "receive_id": chat_id,
            "msg_type": "post",
            "content": json.dumps({
                "post": {
                    "zh_cn": {
                        "title": title,
                        "content": content_lines,
                    }
                }
            }, ensure_ascii=False),
        }

        try:
            async with self._session.post(
                f"{FEISHU_BASE_URL}/im/v1/messages?receive_id_type=open_id",
                json=payload,
                headers=self._auth_headers(token),
            ) as resp:
                data = await resp.json()
                return data.get("code") == 0
        except Exception as e:
            logger.error(f"飞书富文本消息发送异常: {e}")
            return False

    async def broadcast(self, chat_id: str, text: str) -> bool:
        """主动推送消息（兼容 WechatConnection 接口）"""
        return await self.send_text(chat_id, text)
