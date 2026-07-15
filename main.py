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
from src.companion.task_manager import TaskManager
from src.companion.command_dispatcher import CommandDispatcher

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

    # SQLite WAL 模式，防止并发锁
    import sqlite3 as _sqlite3_init
    import os as _os_init
    try:
        _db_init = _os_init.path.expanduser(settings.memory.db_path)
        _conn_init = _sqlite3_init.connect(_db_init, timeout=30)
        _conn_init.execute("PRAGMA journal_mode=WAL")
        _conn_init.execute("PRAGMA busy_timeout=30000")
        _conn_init.commit()
        _conn_init.close()
        logger.info("✅ SQLite WAL 模式已启用")
    except Exception as e:
        logger.warning(f"WAL 模式设置失败: {e}")

    handler = ConversationHandler(settings, llm, memory)

    # 初始化聊天 API（供 /api/chat/history 使用）
    from src.api.chat import init_chat
    init_chat(handler, memory)

    # 初始化所有子系统
    tracker = EmotionTracker(llm, memory)
    report_gen = ReportGenerator(llm, memory)
    daily_report = DailyReportGenerator(llm, memory)
    analyzer = PatternAnalyzer(memory)
    proactive = ProactiveEngine(llm=llm, memory=memory)
    scheduler = CronScheduler()

    # === 注册定时任务 ===

    task_mgr = TaskManager(settings.memory.db_path)
    dispatcher = CommandDispatcher(
        daily_report=daily_report,
        report_gen=report_gen,
        tracker=tracker,
        analyzer=analyzer,
        memory=memory,
        handler=handler,
        task_mgr=task_mgr,
        llm=llm,
    )




    
    # 重新初始化聊天 API，注入任务检测函数
    init_chat(handler, memory, detect_task_list=task_mgr.detect_task_list)
    
    # send_to_user 在 wechat_conn/feishu_conn 定义之后再创建（见下方）

    # 每日 22:00 日报推送
    async def daily_report_task():
        logger.info("📋 生成日报...")
        try:
            report = await daily_report.generate_daily_report()
            logger.info(f"📋 日报生成完成: {report[:100]}...")
            await send_to_user(f"📋 今日日报\n\n{report}")
            task_mgr.mark_done_by_prefix("today-")
        except Exception as e:
            logger.error(f"日报生成失败: {e}")

    # 每日 08:00 主动签到
    async def morning_checkin():
        logger.info("☀️ 早安签到检查...")
        try:
            reminders = await proactive.check_all_rules({"is_morning": True})
            for r in reminders:
                await send_to_user(f"{r.title}\n{r.message}")
        except Exception as e:
            logger.error(f"早安签到失败: {e}")

    # 每 4 小时检查主动提醒
    async def proactive_check():
        logger.info("🔍 主动提醒检查...")
        try:
            reminders = await proactive.check_all_rules()
            for r in reminders:
                await send_to_user(f"{r.title}\n{r.message}")
        except Exception as e:
            logger.error(f"主动提醒检查失败: {e}")

    # 任务到期提醒（每30分钟）
    async def check_pending_task_reminders():
        from datetime import datetime as _dt
        try:
            now = _dt.now()
            today = now.strftime("%Y-%m-%d")
            pending = task_mgr.get_pending_tasks_with_time(today)
            for task in pending:
                task_id, task_date, task_time, task_title = task["id"], task["date"], task["time"], task["title"]
                task_dt = _dt.strptime(f"{task_date} {task_time}", "%Y-%m-%d %H:%M")
                diff_minutes = (task_dt - now).total_seconds() / 60
                if -30 <= diff_minutes <= 30:
                    reminder_key = f"task_reminder_{task_id}_{today}"
                    if reminder_key in scheduler._last_run:
                        continue
                    if diff_minutes > 5:
                        msg = f"📋 {task_title} 将在 {int(diff_minutes)} 分钟后开始 ({task_time})"
                    elif diff_minutes > -5:
                        msg = f"⏰ 现在是：{task_title} ({task_time})"
                    else:
                        msg = f"📌 提醒：{task_title} 已过 {int(abs(diff_minutes))} 分钟 ({task_time})"
                    await send_to_user(msg)
                    from src.memory.base import ConversationMessage as _CM
                    await memory.save_message(_CM(
                        session_id="proactive",
                        role="assistant",
                        content=msg,
                        timestamp=now,
                    ))
                    scheduler._last_run[reminder_key] = now.date()
                    if -5 <= diff_minutes <= 5:
                        task_mgr.update_task_status(task_id, "done")
        except Exception as e:
            logger.error(f"task reminder check failed: {e}")

    scheduler.schedule_daily("daily_report", settings.companion.daily_report_hour, settings.companion.daily_report_minute, daily_report_task)
    scheduler.schedule_daily("morning_checkin", 8, 0, morning_checkin)
    scheduler.schedule_interval("proactive_check", 4 * 3600, proactive_check)
    scheduler.schedule_interval("task_reminder_check", 30 * 60, check_pending_task_reminders)

    # 自动创建今日内置任务
    async def _ensure_builtin_tasks():
        """创建当天的内置系统任务（早间签到、主动关怀检查、每日日报生成）"""
        task_mgr.ensure_builtin_tasks()

    # 启动时立即创建今天的内置任务
    try:
        _loop = asyncio.get_event_loop()
        _loop.create_task(_ensure_builtin_tasks())
    except Exception:
        pass

    # 注册跨天回调：每天0点过后自动创建新一天的内置任务
    scheduler.on_date_change(_ensure_builtin_tasks)

    # === Web API 服务 ===
    web_app = None
    try:
        from src.api.phone import create_phone_router
        from src.dashboard.app import create_dashboard_router
        from src.api.chat import create_chat_router
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
        web_app.include_router(create_dashboard_router())
        web_app.include_router(create_chat_router())

        @web_app.get("/")
        async def root():
            return {"name": "小柏 Agent", "version": "0.3.0", "status": "running"}

        @web_app.get("/api/health")
        async def health_check():
            """健康检查端点"""
            return {"status": "ok", "timestamp": datetime.now().isoformat()}

        @web_app.get("/api/stats")
        async def get_stats():
            return await memory.get_stats()

        @web_app.get("/api/emotions/summary")
        async def get_emotion_summary(days: int = 7):
            return await tracker.get_emotion_summary(days)

        @web_app.get("/api/tasks")
        async def get_tasks(date: str = ""):
            if date:
                tasks = task_mgr.get_tasks_for_date(date)
            else:
                tasks = task_mgr.get_all_tasks()
            return {"tasks": tasks}

        @web_app.get("/api/tasks/today")
        async def get_today_tasks():
            from datetime import datetime as _dt
            _today = _dt.now().strftime("%Y-%m-%d")
            return {"date": _today, "tasks": task_mgr.get_today_tasks()}

        @web_app.post("/api/tasks")
        async def create_task(title: str = "", date: str = "", time: str = "", task_type: str = "user"):
            _tid = task_mgr.create_task(title, date, time, task_type)
            return {"id": _tid, "status": "created"}

        @web_app.put("/api/tasks/{task_id}/status")
        async def update_task_status(task_id: str, status: str = "done"):
            task_mgr.update_task_status(task_id, status)
            return {"status": "updated"}

        @web_app.get("/api/tasks/upcoming")
        async def get_upcoming_tasks():
            from datetime import datetime as _dt, timedelta as _td
            _tomorrow = (_dt.now() + _td(days=1)).strftime("%Y-%m-%d")
            return {"tasks": task_mgr.get_pending_tasks_with_time(_tomorrow)}

        # === 飞书 Webhook 路由（集成到8088端口） ===
        import json as _json
        from fastapi import Request
        
        @web_app.post("/feishu/webhook")
        async def feishu_webhook(request: Request):
            """处理飞书 Webhook 回调"""
            try:
                body = await request.json()
            except Exception:
                return {"error": "invalid json"}
            
            # URL 验证（飞书首次配置时会发送）
            if body.get("type") == "url_verification":
                return {"challenge": body.get("challenge", "")}
            
            # 验证 token
            token = body.get("token", "")
            if settings.feishu.verification_token and token != settings.feishu.verification_token:
                logger.warning(f"飞书 Webhook token 验证失败: {token}")
                return {"error": "invalid token"}
            
            # 处理事件
            event = body.get("event", {})
            event_type = body.get("header", {}).get("event_type", "")
            
            if event_type == "im.message.receive_v1":
                # 提取消息内容
                message = event.get("message", {})
                sender = event.get("sender", {}).get("sender_id", {})
                
                msg_type = message.get("message_type", "")
                chat_id = message.get("chat_id", "")
                chat_type = message.get("chat_type", "p2p")
                msg_id = message.get("message_id", "")
                
                # 只处理文本消息
                if msg_type == "text":
                    content = message.get("content", "{}")
                    try:
                        content_obj = _json.loads(content)
                        text = content_obj.get("text", "").strip()
                    except (_json.JSONDecodeError, TypeError):
                        text = content
                    
                    # 去掉 @机器人 的部分
                    mentions = message.get("mentions", [])
                    for mention in mentions:
                        key = mention.get("key", "")
                        if key:
                            text = text.replace(key, "").strip()
                    
                    if text and feishu_conn:
                        logger.info(f"收到飞书消息: [{chat_type}] {text[:50]}")
                        
                        # 创建飞书消息对象
                        from src.feishu.connection import FeishuMessage
                        feishu_msg = FeishuMessage(
                            msg_id=msg_id,
                            sender_id=sender.get("open_id", ""),
                            sender_name=sender.get("open_id", ""),
                            content=text,
                            chat_id=chat_id,
                            chat_type=chat_type,
                            msg_type=msg_type,
                        )
                        
                        # 调用消息处理器
                        if hasattr(feishu_conn, '_on_message') and feishu_conn._on_message:
                            try:
                                await feishu_conn._on_message(feishu_msg)
                            except Exception as e:
                                logger.error(f"处理飞书消息失败: {e}")
            
            return {"code": 0}
        
        logger.info("📱 飞书 Webhook 路由已注册: /feishu/webhook")
    
    except Exception as e:
        logger.warning(f"Web API 初始化失败: {e}")

    # === 微信连接 ===
    wechat_conn = None
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

    # === 飞书连接 ===
    feishu_conn = None
    from src.feishu.connection import FeishuConnection, FeishuConfig
    if settings.feishu.enabled and settings.feishu.app_id and settings.feishu.app_secret:
        try:
            feishu_config = FeishuConfig(
                app_id=settings.feishu.app_id,
                app_secret=settings.feishu.app_secret,
                encrypt_key=settings.feishu.encrypt_key or "",
                verification_token=settings.feishu.verification_token or "",
                webhook_port=settings.feishu.webhook_port,
            )
            feishu_conn = FeishuConnection(config=feishu_config)
            await feishu_conn.start()
            logger.info("📱 飞书连接已启动")
        except ImportError:
            logger.warning("飞书连接需要 aiohttp: pip install aiohttp")
        except Exception as e:
            logger.error(f"飞书连接失败: {e}")
    elif settings.feishu.enabled and not settings.feishu.app_id:
        logger.warning("📱 飞书已启用但未配置 app_id，请检查 config.yaml")

    # === send_to_user（必须在 wechat_conn/feishu_conn 之后定义）===
    async def send_to_user(msg: str):
        """发送消息给用户（优先飞书，其次微信）"""
        if feishu_conn and settings.feishu.owner_id:
            try:
                await feishu_conn.broadcast(settings.feishu.owner_id, msg)
                logger.info(f"📤 主动提醒已发送(飞书): {msg[:50]}...")
            except Exception as e:
                logger.error(f"飞书发送提醒失败: {e}")
        elif wechat_conn and settings.wechat.owner_id:
            try:
                await wechat_conn.broadcast(settings.wechat.owner_id, msg)
                logger.info(f"📤 主动提醒已发送(微信): {msg[:50]}...")
            except Exception as e:
                logger.error(f"微信发送提醒失败: {e}")
        else:
            logger.warning(f"无法发送提醒（飞书/微信均未连接）: {msg[:50]}...")

    # === 启动所有服务 ===
    # === 飞书消息处理 ===
    if feishu_conn:
        async def handle_feishu_message(msg):
            """处理飞书消息"""
            logger.info(f"收到飞书消息 [{msg.sender_name}]: {msg.content}")
            handler.start_session()
            
            response = await dispatcher.dispatch(msg.content)
            await feishu_conn.broadcast(msg.chat_id, response)
            
            logger.info(f"已回复飞书 [{msg.sender_name}]")
        
        feishu_conn.on_message(handle_feishu_message)
        logger.info("📱 飞书消息处理器已注册")
    
    logger.info(f"🌟 小柏守护模式启动！")
    logger.info(f"   模型: {llm.name}")
    logger.info(f"   定时任务: 日报({settings.companion.daily_report_hour}:00), 签到(8:00), 主动提醒(每4h), 任务提醒(每30min)")
    if wechat_conn:
        logger.info(f"   微信: 已连接")
    else:
        logger.info(f"   微信: 未配置（仅交互模式可用）")
    if feishu_conn:
        logger.info(f"   飞书: 已连接")

    # 启动 Web 服务（后台）
    web_task = None
    web_server = None
    if web_app:
        try:
            import uvicorn
            config = uvicorn.Config(web_app, host="0.0.0.0", port=8088, log_level="warning")
            web_server = uvicorn.Server(config)
            web_task = asyncio.create_task(web_server.serve())
            logger.info(f"   Web API: http://0.0.0.0:8088")
        except Exception as e:
            logger.warning(f"Web 服务启动失败: {e}")

    async def _monitor_web_server():
        """监控 Web 服务，崩溃时自动重启"""
        nonlocal web_task, web_server
        await asyncio.sleep(5)  # 等待首次启动
        while True:
            if web_task and web_task.done():
                try:
                    exc = web_task.exception()
                    logger.error(f"❌ Web 服务已崩溃: {exc}")
                except asyncio.CancelledError:
                    logger.error("❌ Web 服务被取消")
                except Exception:
                    logger.error("❌ Web 服务异常退出（原因未知）")
                
                # 尝试重启
                try:
                    import uvicorn
                    config = uvicorn.Config(web_app, host="0.0.0.0", port=8088, log_level="warning")
                    web_server = uvicorn.Server(config)
                    web_task = asyncio.create_task(web_server.serve())
                    logger.info("🔄 Web 服务已重启")
                except Exception as e:
                    logger.error(f"❌ Web 服务重启失败: {e}")
            
            await asyncio.sleep(10)  # 每10秒检查一次

    if web_app:
        asyncio.create_task(_monitor_web_server())

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

                    response = await dispatcher.dispatch(msg.content)
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
    if feishu_conn:
        await feishu_conn.stop()
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
