"""小柏 Agent - 主入口

个人数字伙伴系统
- 分层记忆：原始对话 / 提取事实 / 情绪追踪 / 关联索引
- LLM 支持：Ollama (本地) / OpenAI 兼容 API
- 微信连接：基于 Hermes iLink Bot API
- 主动提醒：情绪关怀、屏幕时间、每日签到
- 报告生成：日报、周报、月报
- 模式分析：行为规律、情绪预测
- 手机监控：接收 Android 上报数据

用法：
  python main.py                    # 交互模式（终端对话）
  python main.py --daemon           # 守护模式（微信 + 定时任务 + API 服务）
  python main.py --test             # 测试模式（验证配置）
  python main.py --web              # Web API 模式
"""

import argparse
import asyncio
import logging
import signal
import sys
from datetime import datetime

from config.settings import load_settings
from src.companion.handler import ConversationHandler
from src.companion.emotion_tracker import EmotionTracker
from src.companion.daily_report import DailyReportGenerator
from src.companion.report_generator import ReportGenerator
from src.companion.pattern_analyzer import PatternAnalyzer
from src.companion.proactive import ProactiveEngine
from src.companion.scheduler import CronScheduler
from src.llm.factory import create_llm_provider
from src.memory.database import MemoryDatabase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("xiaobo")


async def interactive_mode(settings):
    """交互模式 - 终端对话"""
    llm = create_llm_provider(settings.llm)
    memory = MemoryDatabase(settings.memory.db_path)
    await memory.initialize()

    handler = ConversationHandler(settings, llm, memory)
    session_id = handler.start_session()

    print(f"\n🌟 小柏已上线！你好 {settings.companion.user_name}！")
    print(f"   模型: {llm.name}")
    print(f"   记忆库: {settings.memory.db_path}")
    print(f"   输入 'quit' 退出，'stats' 查看记忆统计")
    print(f"   命令: 'report' 生成日报 | 'mood' 情绪摘要 | 'pattern' 行为分析\n")

    try:
        while True:
            try:
                user_input = input(f"{settings.companion.user_name}: ").strip()
            except EOFError:
                break

            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit", "q"):
                print("👋 再见！")
                break
            if user_input.lower() == "stats":
                stats = await memory.get_stats()
                print(f"📊 记忆统计: {stats}")
                continue
            if user_input.lower() == "report":
                reporter = DailyReportGenerator(llm, memory)
                report = await reporter.generate_daily_report()
                print(f"\n📋 今日日报:\n{report}\n")
                continue
            if user_input.lower() == "mood":
                tracker = EmotionTracker(llm, memory)
                summary = await tracker.get_emotion_summary(days=7)
                print(f"\n🎭 情绪摘要:\n{summary}\n")
                continue
            if user_input.lower() == "pattern":
                analyzer = PatternAnalyzer(memory)
                pattern = await analyzer.analyze_weekly_pattern()
                print(f"\n📊 本周模式:")
                print(f"  总消息: {pattern['total_messages']}")
                print(f"  最忙: {pattern['busiest_day']}")
                print(f"  最闲: {pattern['quietest_day']}")
                changes = await analyzer.detect_habit_changes()
                for c in changes:
                    print(f"  {c}")
                print()
                continue
            if user_input.lower() == "week":
                gen = ReportGenerator(llm, memory)
                report = await gen.generate_weekly_report()
                print(f"\n📋 周报:\n{report}\n")
                continue
            if user_input.lower() == "month":
                gen = ReportGenerator(llm, memory)
                report = await gen.generate_monthly_report()
                print(f"\n📋 月报:\n{report}\n")
                continue

            response = await handler.handle_message(user_input)
            print(f"\n{settings.companion.name}: {response}\n")

    finally:
        await memory.close()
        await llm.close()


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


async def daemon_mode(settings):
    """守护模式 - 微信 + 定时任务 + Web API"""
    llm = create_llm_provider(settings.llm)
    memory = MemoryDatabase(settings.memory.db_path)
    await memory.initialize()

    handler = ConversationHandler(settings, llm, memory)

    # 初始化所有子系统
    tracker = EmotionTracker(llm, memory)
    report_gen = ReportGenerator(llm, memory)
    daily_report = DailyReportGenerator(llm, memory)
    analyzer = PatternAnalyzer(memory)
    proactive = ProactiveEngine(llm=llm, memory=memory)
    scheduler = CronScheduler()

    # === 注册定时任务 ===

    # 每日 22:00 日报推送
    async def daily_report_task():
        logger.info("📋 生成日报...")
        try:
            report = await daily_report.generate_daily_report()
            logger.info(f"📋 日报生成完成: {report[:100]}...")
            # 通过微信推送（如果有连接）
            if wechat_conn:
                await wechat_conn.broadcast(settings.wechat.owner_id, f"📋 今日日报\n\n{report}")
        except Exception as e:
            logger.error(f"日报生成失败: {e}")

    # 每日 08:00 主动签到
    async def morning_checkin():
        logger.info("☀️ 早安签到检查...")
        try:
            reminders = await proactive.check_all_rules({"is_morning": True})
            for r in reminders:
                if wechat_conn and settings.wechat.owner_id:
                    await wechat_conn.broadcast(settings.wechat.owner_id, f"{r.title}\n{r.message}")
        except Exception as e:
            logger.error(f"早安签到失败: {e}")

    # 每 4 小时检查主动提醒
    async def proactive_check():
        logger.info("🔍 主动提醒检查...")
        try:
            reminders = await proactive.check_all_rules()
            for r in reminders:
                if wechat_conn and settings.wechat.owner_id:
                    await wechat_conn.broadcast(settings.wechat.owner_id, f"{r.title}\n{r.message}")
        except Exception as e:
            logger.error(f"主动提醒检查失败: {e}")

    scheduler.schedule_daily("daily_report", settings.companion.daily_report_hour, settings.companion.daily_report_minute, daily_report_task)
    scheduler.schedule_daily("morning_checkin", 8, 0, morning_checkin)
    scheduler.schedule_interval("proactive_check", 4 * 3600, proactive_check)

    # === Web API 服务 ===
    web_app = None
    try:
        from src.api.phone import create_phone_router
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware

        web_app = FastAPI(title="小柏 Agent API", version="0.3.0")
        web_app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
        web_app.include_router(create_phone_router())

        @web_app.get("/")
        async def root():
            return {"name": "小柏 Agent", "version": "0.3.0", "status": "running"}

        @web_app.get("/api/stats")
        async def get_stats():
            return await memory.get_stats()

        @web_app.get("/api/emotions/summary")
        async def get_emotion_summary(days: int = 7):
            return await tracker.get_emotion_summary(days)

    except Exception as e:
        logger.warning(f"Web API 初始化失败: {e}")

    # === 微信连接 ===
    wechat_conn = None
    # 优先使用已保存的 token 文件
    from src.wechat.connection import WechatConnection
    saved_token = WechatConnection.load_token()
    token = saved_token or settings.wechat.ilink_token

    if settings.wechat.enabled and token:
        try:
            wechat_conn = WechatConnection(token=token)
            await wechat_conn.start()
            logger.info("📱 微信连接已启动")
        except ImportError:
            logger.warning("微信连接需要 aiohttp: pip install aiohttp")
        except Exception as e:
            logger.error(f"微信连接失败: {e}")
    elif settings.wechat.enabled and not token:
        logger.warning("📱 微信已启用但未登录，请先运行: python main.py --qr-login")

    # === 启动所有服务 ===
    logger.info(f"🌟 小柏守护模式启动！")
    logger.info(f"   模型: {llm.name}")
    logger.info(f"   定时任务: 日报({settings.companion.daily_report_hour}:00), 签到(8:00), 主动提醒(每4h)")
    if wechat_conn:
        logger.info(f"   微信: 已连接")
    else:
        logger.info(f"   微信: 未配置（仅交互模式可用）")

    # 启动 Web 服务（后台）
    web_task = None
    if web_app:
        try:
            import uvicorn
            config = uvicorn.Config(web_app, host="0.0.0.0", port=8088, log_level="warning")
            server = uvicorn.Server(config)
            web_task = asyncio.create_task(server.serve())
            logger.info(f"   Web API: http://0.0.0.0:8088")
        except Exception as e:
            logger.warning(f"Web 服务启动失败: {e}")

    # 启动定时调度
    scheduler_task = asyncio.create_task(scheduler.start())

    # 微信消息处理循环
    if wechat_conn:
        try:
            while True:
                messages = await wechat_conn.poll_messages()
                for msg in messages:
                    logger.info(f"收到消息 [{msg.sender_name}]: {msg.content}")
                    handler.start_session()

                    # 处理特殊命令
                    if msg.content.strip() == "日报":
                        report = await daily_report.generate_daily_report()
                        await wechat_conn.broadcast(msg.sender_id, f"📋 今日日报\n\n{report}")
                    elif msg.content.strip() == "周报":
                        report = await report_gen.generate_weekly_report()
                        await wechat_conn.broadcast(msg.sender_id, f"📋 周报\n\n{report}")
                    elif msg.content.strip() == "月报":
                        report = await report_gen.generate_monthly_report()
                        await wechat_conn.broadcast(msg.sender_id, f"📋 月报\n\n{report}")
                    elif msg.content.strip() == "情绪":
                        summary = await tracker.get_emotion_summary(days=7)
                        await wechat_conn.broadcast(msg.sender_id, f"🎭 情绪摘要\n\n{summary}")
                    elif msg.content.strip() == "模式":
                        pattern = await analyzer.analyze_weekly_pattern()
                        text = f"📊 本周模式\n总消息: {pattern['total_messages']}\n最忙: {pattern['busiest_day']}\n最闲: {pattern['quietest_day']}"
                        await wechat_conn.broadcast(msg.sender_id, text)
                    elif msg.content.strip() == "统计":
                        stats = await memory.get_stats()
                        await wechat_conn.broadcast(msg.sender_id, f"📊 记忆统计: {stats}")
                    else:
                        response = await handler.handle_message(msg.content)
                        await wechat_conn.broadcast(msg.sender_id, response)

                    logger.info(f"已回复 [{msg.sender_name}]")
        except KeyboardInterrupt:
            pass
    else:
        # 无微信连接时，保持 API 服务运行
        logger.info("无微信连接，仅 API 服务运行中。按 Ctrl+C 退出。")
        try:
            while True:
                await asyncio.sleep(60)
        except KeyboardInterrupt:
            pass

    # 关闭
    logger.info("🛑 正在关闭...")
    scheduler.stop()
    if web_task:
        web_task.cancel()
    if wechat_conn:
        await wechat_conn.stop()
    await memory.close()
    await llm.close()


async def web_mode(settings):
    """Web API 模式 - 仅启动 API 服务"""
    from src.api.phone import create_phone_router
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    import uvicorn

    llm = create_llm_provider(settings.llm)
    memory = MemoryDatabase(settings.memory.db_path)
    await memory.initialize()

    app = FastAPI(title="小柏 Agent API", version="0.3.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(create_phone_router())

    @app.get("/")
    async def root():
        return {"name": "小柏 Agent", "version": "0.3.0", "status": "running"}

    @app.get("/api/stats")
    async def get_stats():
        return await memory.get_stats()

    print(f"🌐 小柏 API 服务启动: http://0.0.0.0:8088")
    config = uvicorn.Config(app, host="0.0.0.0", port=8088)
    server = uvicorn.Server(config)
    await server.serve()


async def test_mode(settings):
    """测试模式 - 验证配置和连接"""
    print("🔍 测试模式 - 验证系统配置\n")

    # 测试 LLM
    print("1. 测试 LLM 连接...")
    llm = create_llm_provider(settings.llm)
    healthy = await llm.health_check()
    if healthy:
        print(f"   ✅ {llm.name} 连接正常")
    else:
        print(f"   ❌ {llm.name} 连接失败")
        await llm.close()
        return False

    # 测试记忆数据库
    print("2. 测试记忆数据库...")
    memory = MemoryDatabase(settings.memory.db_path)
    try:
        await memory.initialize()
        stats = await memory.get_stats()
        print(f"   ✅ 数据库正常: {stats}")
    except Exception as e:
        print(f"   ❌ 数据库异常: {e}")
        await memory.close()
        await llm.close()
        return False

    # 测试 LLM 对话
    print("3. 测试 LLM 对话...")
    from src.llm.base import ChatMessage
    try:
        response = await llm.chat([
            ChatMessage(role="user", content="说一个字：好")
        ])
        print(f"   ✅ LLM 回复: {response.content[:50]}")
    except Exception as e:
        print(f"   ❌ LLM 对话异常: {e}")

    # 测试主动提醒引擎
    print("4. 测试主动提醒引擎...")
    from src.companion.proactive import ProactiveEngine
    engine = ProactiveEngine(llm=llm, memory=memory)
    rules = engine.get_rules()
    print(f"   ✅ {len(rules)} 条规则已加载: {[r.name for r in rules]}")

    # 测试报告生成器
    print("5. 测试报告生成器...")
    from src.companion.report_generator import ReportGenerator
    gen = ReportGenerator(llm, memory)
    print(f"   ✅ 日报/周报/月报生成器就绪")

    # 测试模式分析器
    print("6. 测试模式分析器...")
    from src.companion.pattern_analyzer import PatternAnalyzer
    analyzer = PatternAnalyzer(memory)
    print(f"   ✅ 行为分析器就绪")

    await memory.close()
    await llm.close()
    print("\n✅ 所有测试通过！")
    return True


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
        asyncio.run(test_mode(settings))
    elif args.qr_login:
        asyncio.run(qr_login_mode(settings))
    elif args.daemon:
        asyncio.run(daemon_mode(settings))
    elif args.web:
        asyncio.run(web_mode(settings))
    else:
        asyncio.run(interactive_mode(settings))


if __name__ == "__main__":
    main()
