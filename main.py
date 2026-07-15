"""小柏 Agent - 主入口

个人数字伙伴系统

用法：
  python main.py                    # 交互模式（终端对话）
  python main.py --daemon           # 守护模式（微信 + 定时任务 + API 服务）
  python main.py --test             # 测试模式（验证配置）
  python main.py --web              # Web API 模式
  python main.py --qr-login        # 微信扫码登录
"""

import argparse
import asyncio
import logging

from config.settings import load_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)


def main():
    parser = argparse.ArgumentParser(description="小柏 - 个人数字伙伴")
    parser.add_argument("--daemon", action="store_true", help="守护模式（微信连接 + 定时任务 + API）")
    parser.add_argument("--test", action="store_true", help="测试模式")
    parser.add_argument("--web", action="store_true", help="Web API 模式")
    parser.add_argument("--qr-login", action="store_true", help="微信 QR 扫码登录")
    parser.add_argument("--config", type=str, help="配置文件路径")
    args = parser.parse_args()

    settings = load_settings(args.config)

    if args.test:
        from src.modes.test_mode import test_mode
        asyncio.run(test_mode(settings))
    elif args.qr_login:
        from src.modes.qr_login import qr_login_mode
        asyncio.run(qr_login_mode(settings))
    elif args.daemon:
        from src.modes.daemon import daemon_mode
        asyncio.run(daemon_mode(settings))
    elif args.web:
        from src.modes.web import web_mode
        asyncio.run(web_mode(settings))
    else:
        from src.modes.interactive import interactive_mode
        asyncio.run(interactive_mode(settings))


if __name__ == "__main__":
    main()
