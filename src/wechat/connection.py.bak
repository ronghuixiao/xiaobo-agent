"""微信连接层 - 基于 Hermes iLink Bot API

支持 QR 码登录 + 长轮询收发消息。
"""
import asyncio
import base64
import json
import logging
import secrets
import struct
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    aiohttp = None
    AIOHTTP_AVAILABLE = False

# iLink API 常量
ILINK_BASE_URL = "https://ilinkai.weixin.qq.com"
ILINK_APP_ID = "bot"
CHANNEL_VERSION = "2.2.0"

EP_GET_UPDATES = "ilink/bot/getupdates"
EP_SEND_MESSAGE = "ilink/bot/sendmessage"
EP_SEND_TYPING = "ilink/bot/sendtyping"
EP_GET_BOT_QR = "ilink/bot/get_bot_qrcode"
EP_GET_QR_STATUS = "ilink/bot/get_qrcode_status"

TOKEN_DIR = Path("~/.xiaobo-agent")
TOKEN_FILE = TOKEN_DIR / "wechat_token"


def _random_wechat_uin() -> str:
    value = struct.unpack(">I", secrets.token_bytes(4))[0]
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
    """微信连接管理器

    使用方式:
        conn = WechatConnection()
        token = await conn.qr_login()   # 首次扫码登录
        # 或
        conn = WechatConnection(token="xxx")
        await conn.start()
        messages = await conn.poll_messages()
    """

    def __init__(self, token: str = ""):
        if not AIOHTTP_AVAILABLE:
            raise ImportError("需要安装 aiohttp: pip install aiohttp")
        self.token = token
        self._session: Optional[aiohttp.ClientSession] = None
        self._running = False
        self._context_tokens: Dict[str, str] = {}

    # ==================== Token 管理 ====================

    @staticmethod
    def load_token() -> str:
        """从文件加载已保存的 token"""
        if TOKEN_FILE.exists():
            return TOKEN_FILE.read_text().strip()
        return ""

    @staticmethod
    def save_token(token: str):
        """保存 token 到文件"""
        TOKEN_DIR.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(token)
        logger.info(f"Token 已保存: {TOKEN_FILE}")

    # ==================== 连接管理 ====================

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

    # ==================== QR 登录 ====================

    async def qr_login(self) -> str:
        """QR 码登录流程

        1. 请求 QR 码
        2. 轮询扫码状态
        3. 返回并保存 token
        """
        if not self._session:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=60)
            )

        # Step 1: 获取 QR 码
        logger.info("正在获取微信登录二维码...")
        payload = {
            "base_req": {
                "token": "",
                "client_version": CHANNEL_VERSION,
            }
        }

        qr_ticket = ""
        try:
            async with self._session.post(
                f"{ILINK_BASE_URL}/{EP_GET_BOT_QR}",
                json=payload,
                headers=_headers(),
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()
                logger.info(f"QR 响应: errcode={data.get('errcode', 'N/A')}")

                if data.get("errcode", 0) != 0 and data.get("errcode") is not None:
                    logger.error(f"获取 QR 码失败: {data}")
                    return ""

                qr_url = data.get("qr_url", "")
                qr_ticket = data.get("ticket", "")

                if qr_url:
                    print(f"\n{'='*50}")
                    print(f"📱 请用微信扫描以下二维码:")
                    print(f"{'='*50}")
                    print(f"QR URL: {qr_url}")
                    print(f"{'='*50}\n")
                elif qr_ticket:
                    print(f"\n🎫 Ticket: {qr_ticket}")
                    print("请在微信中扫描二维码...\n")
                else:
                    logger.warning("未获取到 QR 码数据")
                    return ""

        except Exception as e:
            logger.error(f"获取 QR 码异常: {e}")
            return ""

        # Step 2: 轮询扫码状态
        logger.info("等待扫码中...")
        max_wait = 120
        poll_interval = 2

        for i in range(max_wait // poll_interval):
            await asyncio.sleep(poll_interval)

            try:
                status_payload = {
                    "base_req": {
                        "token": qr_ticket,
                        "client_version": CHANNEL_VERSION,
                    }
                }
                async with self._session.post(
                    f"{ILINK_BASE_URL}/{EP_GET_QR_STATUS}",
                    json=status_payload,
                    headers=_headers(),
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    status_data = await resp.json()
                    errcode = status_data.get("errcode", -1)

                    if errcode == 0:
                        token = status_data.get("token", "")
                        if token:
                            self.token = token
                            self.save_token(token)
                            print(f"✅ 微信登录成功！")
                            return token
                    elif errcode == -14:
                        logger.info("二维码已过期，重新获取中...")
                        return await self.qr_login()
                    else:
                        if i % 5 == 0:
                            logger.info(f"等待扫码... ({i*poll_interval}s)")

            except Exception as e:
                logger.warning(f"轮询扫码状态异常: {e}")

        logger.warning("等待扫码超时")
        return ""

    # ==================== 消息收发 ====================

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

                # Session expired
                if data.get("errcode") == -14:
                    logger.warning("Session 过期，需要重新扫码")
                    return []

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
            context_token = item.get("context_token", "")

            text = ""
            for ci in content_items:
                if ci.get("type") == 1:  # TEXT
                    text = ci.get("text", "")
                    break

            if not text:
                return None

            sender_id = str(sender.get("id", ""))
            if sender_id and context_token:
                self._context_tokens[sender_id] = context_token

            return WechatMessage(
                msg_id=msg_id,
                sender_id=sender_id,
                sender_name=sender.get("name", ""),
                content=text,
                msg_type=item.get("msg_type", 1),
                context_token=context_token,
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

    async def broadcast(self, peer_id: str, text: str) -> bool:
        """主动推送消息"""
        return await self.send_text(peer_id, text)
