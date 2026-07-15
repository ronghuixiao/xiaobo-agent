"""QR 扫码登录模式 - 扫码获取微信 token"""


async def qr_login_mode(settings):
    """QR 扫码登录模式 - 扫码获取微信 token"""
    try:
        from src.wechat.connection import WechatConnection
    except ImportError:
        print("❌ 需要 aiohttp: pip install aiohttp")
        return

    conn = WechatConnection()
    print("\n📱 微信 QR 扫码登录")
    print("=" * 50)
    token = await conn.qr_login()
    if token:
        print(f"\n✅ 登录成功！Token 已保存")
        print(f"   现在可以用 'python main.py --daemon' 启动守护模式")
        print(f"   Token 文件: ~/.xiaobo-agent/wechat_token")
    else:
        print("\n❌ 登录失败或超时，请重试")
