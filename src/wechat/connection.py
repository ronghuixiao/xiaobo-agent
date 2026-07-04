"""微信连接层 - 基于 Hermes iLink Bot API

参考 Hermes 的 weixin.py 实现，简化为：
- QR 码登录
- 长轮询接收消息
- 发送文本消息

完整版需要 cryptography 库（AES 加密 CDN 媒体）。
"""

import asyncio
import json
import logging
import secrets
import struct
import time
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

# iLink API 常量（来自 Hermes）
ILINK_BASE_URL = "https://ilinkai.weixin.qq.com"
ILINK_APP_ID = "bot"
CHANNEL_VERSION = "2.2.0"
LONG_POLL_TIMEOUT_MS = 35_000

EP_GET_UPDATES = "ilink/bot/getupdates"
EP_SEND_MESSAGE = "ilink/bot/sendmessage"
EP_SEND_TYPING = "ilink/bot/sendtyping"
EP_GET_BOT_QR = "ilink/bot/get_bot_qrcode"
EP_GET_QR_STATUS = "ilink/bot/get_qrcode_status"


def _random_wechat_uin() -> str:
    value = struct.unpack(">I", secrets.token_bytes(4))[0]
    import base64
    return base64.b64encode(str(value).encode("utf-8")).decode("ascii")


def _headers(token: Optional[str] = None) -> Dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "X-WECHAT-UIN": _random_wechat_uin(),
        "iLink-App-Id": ILINK_APP_ID,
        "iLink-App-Version": CHANNEL_VERSION,
    }
    if token:
        headers["Authorization"] = token
    return headers


class WechatMessage:
    """微信消息"""
    def __init__(
        self,
        msg_id: str = "",
        sender_id: str = "",
        sender_name: str = "",
        content: str = "",
        msg_type: int = 1,
        context_token: str = "",
    ):
        self.msg_id = msg_id
        self.sender_id = sender_id
        self.sender_name = sender_name
        self.content = content
        self.msg_type = msg_type
        self.context_token = context_token


class WechatConnection:
    """微信连接管理器"""

    def __init__(self, token: str = ""):
        if not AIOHTTP_AVAILABLE:
            raise ImportError("需要安装 aiohttp: pip install aiohttp")

        self.token = token
        self._session: Optional[aiohttp.ClientSession] = None
        self._running = False
        self._context_tokens: Dict[str, str] = {}  # peer_id -> context_token

    async def start(self):
        """启动连接"""
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=60)
        )
        self._running = True
        logger.info("微信连接已启动")

    async def stop(self):
        """停止连接"""
        self._running = False
        if self._session:
            await self._session.close()
        logger.info("微信连接已关闭")

    async def poll_messages(self) -> List[WechatMessage]:
        """长轮询获取新消息"""
        if not self._session or not self._running:
            return []

        payload = {
            "base_req": {
                "token": self.token,
                "client_version": CHANNEL_VERSION,
            }
        }

        try:
            async with self._session.post(
                f"{ILINK_BASE_URL}/{EP_GET_UPDATES}",
                json=payload,
                headers=_headers(self.token),
                timeout=aiohttp.ClientTimeout(total=40),
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"轮询失败: HTTP {resp.status}")
                    return []

                data = await resp.json()
                messages = []

                for item in data.get("messages", []):
                    msg = self._parse_message(item)
                    if msg:
                        messages.append(msg)

                return messages

        except asyncio.TimeoutError:
            return []
        except Exception as e:
            logger.error(f"轮询异常: {e}")
            return []

    def _parse_message(self, item: Dict[str, Any]) -> Optional[WechatMessage]:
        """解析 iLink 消息格式"""
        try:
            msg_id = str(item.get("msg_id", ""))
            sender = item.get("sender", {})
            content_items = item.get("content", [])

            # 提取文本内容
            text = ""
            for ci in content_items:
                if ci.get("type") == 1:  # TEXT
                    text = ci.get("text", "")
                    break

            if not text:
                return None

            return WechatMessage(
                msg_id=msg_id,
                sender_id=str(sender.get("id", "")),
                sender_name=sender.get("name", ""),
                content=text,
                msg_type=item.get("msg_type", 1),
                context_token=item.get("context_token", ""),
            )
        except Exception as e:
            logger.warning(f"消息解析失败: {e}")
            return None

    async def send_text(self, peer_id: str, text: str) -> bool:
        """发送文本消息"""
        if not self._session or not self._running:
            return False

        context_token = self._context_tokens.get(peer_id, "")

        payload = {
            "base_req": {
                "token": self.token,
                "client_version": CHANNEL_VERSION,
            },
            "to_user": peer_id,
            "context_token": context_token,
            "content": [{"type": 1, "text": text}],
        }

        try:
            async with self._session.post(
                f"{ILINK_BASE_URL}/{EP_SEND_MESSAGE}",
                json=payload,
                headers=_headers(self.token),
            ) as resp:
                data = await resp.json()
                if data.get("errcode", 0) != 0:
                    logger.warning(f"发送失败: {data}")
                    return False
                return True
        except Exception as e:
            logger.error(f"发送异常: {e}")
            return False
