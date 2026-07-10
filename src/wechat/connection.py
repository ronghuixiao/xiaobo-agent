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

# iLink bot_type: 3 = 个人微信扫码登录
ILINK_BOT_TYPE = "3"

TOKEN_DIR = Path("~/.xiaobo-agent").expanduser()
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
        headers["Authorization"] = f"Bearer {token}"
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
        self._sync_buf: str = ""  # 长轮询同步缓冲

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

        1. GET 请求获取 QR 码
        2. GET 长轮询扫码状态 (status 字段: wait/scaned/confirmed/expired)
        3. 返回并保存 token
        """
        if not self._session:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=60),
                trust_env=True,
            )

        # Step 1: 获取 QR 码 (GET 请求)
        logger.info("正在获取微信登录二维码...")
        qr_headers = {
            "iLink-App-Id": ILINK_APP_ID,
            "iLink-App-ClientVersion": CHANNEL_VERSION,
        }

        qrcode_value = ""
        qr_url = ""
        try:
            url = f"{ILINK_BASE_URL}/{EP_GET_BOT_QR}?bot_type={ILINK_BOT_TYPE}"
            async with self._session.get(
                url,
                headers=qr_headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                raw = await resp.read()
                data = json.loads(raw)

                if data.get("ret", -1) != 0:
                    logger.error(f"获取 QR 码失败: {data}")
                    return ""

                qrcode_value = str(data.get("qrcode") or "")
                qr_url = str(data.get("qrcode_img_content") or "")

                if not qrcode_value:
                    logger.error("QR 响应缺少 qrcode 字段")
                    return ""

                print(f"\n{'='*50}")
                print(f"📱 请用微信扫描以下二维码:")
                print(f"{'='*50}")
                if qr_url:
                    print(f"QR URL: {qr_url}")
                print(f"{'='*50}\n")

        except Exception as e:
            logger.error(f"获取 QR 码异常: {e}")
            return ""

        # Step 2: 轮询扫码状态 (GET 长轮询)
        logger.info("等待扫码中...")
        import time
        deadline = time.time() + 300  # 5 分钟超时
        refresh_count = 0

        while time.time() < deadline:
            try:
                status_url = f"{ILINK_BASE_URL}/{EP_GET_QR_STATUS}?qrcode={qrcode_value}"
                async with self._session.get(
                    status_url,
                    headers=qr_headers,
                    timeout=aiohttp.ClientTimeout(total=35),
                ) as resp:
                    raw = await resp.read()
                    status_data = json.loads(raw)

                    status = str(status_data.get("status") or "wait")

                    if status == "wait":
                        print(".", end="", flush=True)
                    elif status == "scaned":
                        print("\n已扫码，请在微信里确认...")
                    elif status == "scaned_but_redirect":
                        redirect_host = str(status_data.get("redirect_host") or "")
                        if redirect_host:
                            logger.info(f"重定向到: {redirect_host}")
                            # 更新 base_url 用于后续请求
                    elif status == "expired":
                        refresh_count += 1
                        if refresh_count > 3:
                            print("\n二维码多次过期，请重新执行登录。")
                            return ""
                        print(f"\n二维码已过期，正在刷新... ({refresh_count}/3)")
                        try:
                            async with self._session.get(
                                f"{ILINK_BASE_URL}/{EP_GET_BOT_QR}?bot_type={ILINK_BOT_TYPE}",
                                headers=qr_headers,
                                timeout=aiohttp.ClientTimeout(total=15),
                            ) as refresh_resp:
                                refresh_raw = await refresh_resp.read()
                                refresh_data = json.loads(refresh_raw)
                                qrcode_value = str(refresh_data.get("qrcode") or "")
                                qr_url = str(refresh_data.get("qrcode_img_content") or "")
                                if qr_url:
                                    print(f"新二维码: {qr_url}")
                        except Exception as exc:
                            logger.error(f"刷新二维码失败: {exc}")
                            return ""
                    elif status == "confirmed":
                        account_id = str(status_data.get("ilink_bot_id") or "")
                        token = str(status_data.get("bot_token") or "")
                        base_url = str(status_data.get("baseurl") or ILINK_BASE_URL)

                        if not account_id or not token:
                            logger.error("扫码确认但凭据不完整")
                            return ""

                        self.token = token
                        self.save_token(token)
                        print(f"\n✅ 微信登录成功！account_id={account_id}")
                        return token

            except asyncio.TimeoutError:
                # 长轮询超时是正常的，继续轮询
                continue
            except Exception as exc:
                logger.warning(f"轮询异常: {exc}")
                await asyncio.sleep(1)
                continue

            await asyncio.sleep(1)

        logger.warning("等待扫码超时")
        return ""

    async def close(self):
        """关闭 session"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    # ==================== 消息收发 ====================

    async def poll_messages(self) -> List[WechatMessage]:
        """长轮询获取新消息"""
        if not self._session or not self._running:
            return []

        # Hermes 格式: get_updates_buf 做长轮询
        payload = {
            "get_updates_buf": self._sync_buf,
            "base_info": {"channel_version": CHANNEL_VERSION},
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

                raw = await resp.read()
                try:
                    data = json.loads(raw)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    logger.warning(f"轮询响应解析失败: {raw[:100]!r}")
                    return []

                # 更新 sync_buf
                self._sync_buf = data.get("get_updates_buf", self._sync_buf)

                # Session expired
                if data.get("ret") == -14:
                    logger.warning("Session 过期，需要重新扫码")
                    return []

                messages = []
                for item in data.get("msgs", []):
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
        """解析 iLink 消息格式 (Hermes 兼容)"""
        try:
            # Hermes 格式: from_user_id, item_list, text_item
            from_user_id = str(item.get("from_user_id") or "")
            msg_id = str(item.get("msg_id") or item.get("client_id") or "")
            context_token = str(item.get("context_token") or "")
            item_list = item.get("item_list", [])

            text = ""
            for i in item_list:
                if i.get("type") == 1:  # ITEM_TEXT
                    text = str((i.get("text_item") or {}).get("text") or "")
                    break

            if not text:
                return None

            if from_user_id and context_token:
                self._context_tokens[from_user_id] = context_token

            return WechatMessage(
                msg_id=msg_id,
                sender_id=from_user_id,
                sender_name=item.get("from_nickname", ""),
                content=text,
                msg_type=item.get("msg_type", 1),
                context_token=context_token,
            )
        except Exception as e:
            logger.warning(f"消息解析失败: {e}")
            return None

    async def send_text(self, peer_id: str, text: str) -> bool:
        """发送文本消息 (Hermes 兼容格式)"""
        if not self._session or not self._running:
            return False

        context_token = self._context_tokens.get(peer_id, "")
        import uuid as _uuid
        client_id = str(_uuid.uuid4())

        message = {
            "from_user_id": "",
            "to_user_id": peer_id,
            "client_id": client_id,
            "message_type": 2,  # MSG_TYPE_BOT
            "message_state": 2,  # MSG_STATE_FINISH
            "item_list": [{"type": 1, "text_item": {"text": text}}],
        }
        if context_token:
            message["context_token"] = context_token

        payload = {
            "msg": message,
            "base_info": {"channel_version": CHANNEL_VERSION},
        }

        try:
            async with self._session.post(
                f"{ILINK_BASE_URL}/{EP_SEND_MESSAGE}",
                json=payload,
                headers=_headers(self.token),
            ) as resp:
                # 处理可能的 octet-stream content type
                raw = await resp.read()
                try:
                    data = json.loads(raw)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    logger.warning(f"发送响应解析失败: {raw[:100]!r}")
                    return False
                if data.get("ret", 0) != 0:
                    logger.warning(f"发送失败: {data}")
                    return False
                return True
        except Exception as e:
            logger.error(f"发送异常: {e}")
            return False

    async def broadcast(self, peer_id: str, text: str) -> bool:
        """主动推送消息"""
        return await self.send_text(peer_id, text)
