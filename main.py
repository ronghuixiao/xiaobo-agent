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

    def _mark_task_done(prefix: str):
        import sqlite3 as _sqlite3
        from datetime import datetime as _dt
        try:
            import os as _os; _db = _os.path.expanduser("~/.xiaobo-agent/memory.db")
            _conn = _sqlite3.connect(_db, timeout=10)
            today = _dt.now().strftime("%Y-%m-%d")
            rows = _conn.execute(
                "SELECT id FROM tasks WHERE id LIKE ? AND date = ? AND status = 'pending'",
                (prefix + "%", today)
            ).fetchall()
            for row in rows:
                _conn.execute("UPDATE tasks SET status = 'done' WHERE id = ?", (row[0],))
                logger.info(f"✅ task done: {row[0]}")
            _conn.commit(); _conn.close()
        except Exception as e:
            logger.warning(f"mark task done failed: {e}")

    def _detect_task_list(message: str):
        """检测用户输入的任务列表并保存到数据库
        
        识别格式：
        - 今日任务：A；B；C
        - 任务清单：A、B、C
        - 今天要做：A, B, C
        
        行为：
        - 如果任务已存在且状态为 pending，跳过
        - 如果任务已存在但状态为 done，重置为 pending（用户重新提供清单时）
        - 如果是新任务，添加为 pending
        """
        import sqlite3 as _sqlite3
        from datetime import datetime as _dt
        import os as _os
        import re
        
        # 检测任务列表模式
        patterns = [
            r'今日任务[：:]\s*(.+)',
            r'任务清单[：:]\s*(.+)',
            r'今天要做[：:]\s*(.+)',
            r'今天的任务[：:]\s*(.+)',
            r'今日待办[：:]\s*(.+)',
        ]
        
        tasks = []
        for pattern in patterns:
            match = re.search(pattern, message)
            if match:
                # 提取任务列表（支持；、，,分隔）
                task_str = match.group(1)
                tasks = re.split(r'[；;、，,]', task_str)
                tasks = [t.strip() for t in tasks if t.strip()]
                break
        
        if not tasks:
            return  # 没有检测到任务列表
        
        today = _dt.now().strftime("%Y-%m-%d")
        
        try:
            _db = _os.path.expanduser("~/.xiaobo-agent/memory.db")
            _conn = _sqlite3.connect(_db, timeout=10)
            
            # 获取今天的所有用户任务（包括已完成的）
            existing = _conn.execute(
                "SELECT id, title, status FROM tasks WHERE date = ? AND type = 'user'",
                (today,)
            ).fetchall()
            existing_map = {row[1]: (row[0], row[2]) for row in existing}  # title -> (id, status)
            
            # 处理任务列表
            new_count = 0
            reset_count = 0
            for task_title in tasks:
                if task_title in existing_map:
                    task_id, current_status = existing_map[task_title]
                    if current_status == 'done':
                        # 任务已完成，但用户重新提供清单，重置为 pending
                        _conn.execute(
                            "UPDATE tasks SET status = 'pending' WHERE id = ?",
                            (task_id,)
                        )
                        reset_count += 1
                        logger.info(f"🔄 重置任务: {task_title} (done → pending)")
                    else:
                        # 任务已存在且为 pending，跳过
                        pass
                else:
                    # 新任务，添加
                    task_id = f"user-{today}-{hash(task_title) % 1000000:06d}"
                    _conn.execute(
                        "INSERT INTO tasks (id, title, date, time, status, type, created_at) VALUES (?, ?, ?, '', 'pending', 'user', ?)",
                        (task_id, task_title, today, _dt.now().isoformat())
                    )
                    new_count += 1
                    logger.info(f"📝 新增任务: {task_title}")
            
            if new_count > 0 or reset_count > 0:
                _conn.commit()
                parts = []
                if new_count > 0:
                    parts.append(f"{new_count}个新任务")
                if reset_count > 0:
                    parts.append(f"{reset_count}个重置")
                logger.info(f"✅ 今日任务已更新: {', '.join(parts)}")
            
            _conn.close()
        except Exception as e:
            logger.warning(f"保存任务列表失败: {e}")

    def _detect_task_completion(message: str):
        """使用LLM检测对话中是否提到任务完成，并更新任务状态"""
        import sqlite3 as _sqlite3
        from datetime import datetime as _dt
        import os as _os
        import json as _json
        import asyncio
        import threading
        from src.llm.base import ChatMessage
        
        logger.info(f"🔍 检测任务完成: {message[:50]}...")
        
        def _run_async():
            """在新线程中运行异步检测"""
            async def _async_detect():
                try:
                    _db = _os.path.expanduser("~/.xiaobo-agent/memory.db")
                    _conn = _sqlite3.connect(_db, timeout=10)
                    today = _dt.now().strftime("%Y-%m-%d")
                    
                    # 获取今天的待办任务
                    pending_tasks = _conn.execute(
                        "SELECT id, title FROM tasks WHERE date = ? AND status = 'pending'",
                        (today,)
                    ).fetchall()
                    
                    if not pending_tasks:
                        logger.info("🔍 无待办任务，跳过检测")
                        _conn.close()
                        return
                    
                    logger.info(f"🔍 待办任务: {[t[1] for t in pending_tasks]}")
                    
                    # 构建任务列表
                    task_list = "\n".join([f"- {task_id}: {task_title}" for task_id, task_title in pending_tasks])
                    
                    # 使用LLM判断任务完成
                    prompt = f"""判断用户消息中是否表达了某个任务已完成。
今天的待办任务：
{task_list}
用户消息："{message}"
规则：
- 判断是否表达"完成了/做完了/搞定了/OK了/结束了/通过了/交了/过了"等任何完成含义
- 只匹配列表中的任务
- 返回JSON数组，格式为[{{"task_id": "xxx", "completed": true}}]，没有匹配返回[]
只返回JSON。"""
                    
                    # 调用LLM
                    logger.info("🔍 调用LLM检测...")
                    response = await llm.chat([ChatMessage(role="user", content=prompt)])
                    logger.info(f"🔍 LLM响应: {response.content[:200]}")
                    
                    # 解析LLM返回的JSON
                    try:
                        # 提取JSON部分
                        response_text = response.content
                        start_idx = response_text.find('[')
                        end_idx = response_text.rfind(']') + 1
                        if start_idx != -1 and end_idx != -1:
                            json_str = response_text[start_idx:end_idx]
                            completed_tasks = _json.loads(json_str)
                            logger.info(f"🔍 解析到完成任务: {completed_tasks}")
                            
                            # 更新任务状态
                            for task in completed_tasks:
                                if task.get("completed") and task.get("task_id"):
                                    task_id = task["task_id"]
                                    # 验证任务ID是否在pending列表中
                                    if any(t[0] == task_id for t in pending_tasks):
                                        _conn.execute("UPDATE tasks SET status = 'done' WHERE id = ?", (task_id,))
                                        logger.info(f"✅ 任务已完成(LLM检测): {task_id}")
                                    else:
                                        logger.warning(f"⚠️ 任务ID不在待办列表中: {task_id}")
                        else:
                            logger.info("🔍 LLM响应中未找到JSON数组")
                    except (_json.JSONDecodeError, KeyError, TypeError) as e:
                        logger.warning(f"解析LLM任务完成检测结果失败: {e}")
                    
                    _conn.commit()
                    _conn.close()
                except Exception as e:
                    logger.warning(f"检测任务完成失败: {e}", exc_info=True)
            
            # 运行异步检测
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(_async_detect())
            finally:
                loop.close()
        
        # 在新线程中运行
        thread = threading.Thread(target=_run_async, daemon=True)
        thread.start()
    
    # 重新初始化聊天 API，注入 _detect_task_list 函数
    init_chat(handler, memory, detect_task_list=_detect_task_list)
    
    # send_to_user 在 wechat_conn/feishu_conn 定义之后再创建（见下方）

    # 每日 22:00 日报推送
    async def daily_report_task():
        logger.info("📋 生成日报...")
        try:
            report = await daily_report.generate_daily_report()
            logger.info(f"📋 日报生成完成: {report[:100]}...")
            await send_to_user(f"📋 今日日报\n\n{report}")
            _mark_task_done("today-")
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
        import sqlite3 as _sqlite3
        from datetime import datetime as _dt
        try:
            import os as _os; _db = _os.path.expanduser("~/.xiaobo-agent/memory.db")
            _conn = _sqlite3.connect(_db, timeout=10)
            _conn.row_factory = _sqlite3.Row
            now = _dt.now()
            today = now.strftime("%Y-%m-%d")
            rows = _conn.execute(
                "SELECT * FROM tasks WHERE date <= ? AND status = 'pending' AND time != '' AND time IS NOT NULL ORDER BY date, time",
                (today,)
            ).fetchall()
            _conn.close()
            for row in rows:
                task = dict(row)
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
                        timestamp=_dt.now(),
                    ))
                    scheduler._last_run[reminder_key] = now.date()
                    if -5 <= diff_minutes <= 5:
                        try:
                            _c2 = _sqlite3.connect(_db, timeout=10)
                            _c2.execute("UPDATE tasks SET status = 'done' WHERE id = ?", (task_id,))
                            _c2.commit(); _c2.close()
                        except Exception:
                            pass
        except Exception as e:
            logger.error(f"task reminder check failed: {e}")

    scheduler.schedule_daily("daily_report", settings.companion.daily_report_hour, settings.companion.daily_report_minute, daily_report_task)
    scheduler.schedule_daily("morning_checkin", 8, 0, morning_checkin)
    scheduler.schedule_interval("proactive_check", 4 * 3600, proactive_check)
    scheduler.schedule_interval("task_reminder_check", 30 * 60, check_pending_task_reminders)

    # 自动创建今日内置任务
    async def _ensure_builtin_tasks():
        """创建当天的内置系统任务（早间签到、主动关怀检查、每日日报生成）"""
        import sqlite3 as _sqlite3
        from datetime import datetime as _dt
        import os as _os; _db = _os.path.expanduser("~/.xiaobo-agent/memory.db")
        _conn = _sqlite3.connect(_db, timeout=10)
        today = _dt.now().strftime("%Y-%m-%d")
        existing = _conn.execute("SELECT id FROM tasks WHERE date = ? AND type = 'builtin'", (today,)).fetchall()
        if not existing:
            builtin_tasks = [
                (f"today-{today}-0800", "早间签到", "08:00", today, "pending", "builtin"),
                (f"today-{today}-0900", "主动关怀检查", "09:00", today, "pending", "builtin"),
                (f"today-{today}-2200", "每日日报生成", "22:00", today, "pending", "builtin"),
            ]
            for t in builtin_tasks:
                _conn.execute("INSERT OR IGNORE INTO tasks (id, title, time, date, status, type, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                              (*t, _dt.now().isoformat()))
            _conn.commit()
            logger.info(f"✅ Created {len(builtin_tasks)} builtin tasks for today")
        _conn.close()

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
            import sqlite3 as _sqlite3
            import os as _os; _db = _os.path.expanduser("~/.xiaobo-agent/memory.db")
            _conn = _sqlite3.connect(_db, timeout=10)
            _conn.row_factory = _sqlite3.Row
            if date:
                _rows = _conn.execute("SELECT * FROM tasks WHERE date = ? ORDER BY time", (date,)).fetchall()
            else:
                _rows = _conn.execute("SELECT * FROM tasks ORDER BY date DESC, time").fetchall()
            _conn.close()
            return {"tasks": [dict(_r) for _r in _rows]}

        @web_app.get("/api/tasks/today")
        async def get_today_tasks():
            import sqlite3 as _sqlite3
            from datetime import datetime as _dt
            import os as _os; _db = _os.path.expanduser("~/.xiaobo-agent/memory.db")
            _conn = _sqlite3.connect(_db, timeout=10)
            _conn.row_factory = _sqlite3.Row
            _today = _dt.now().strftime("%Y-%m-%d")
            _rows = _conn.execute("SELECT * FROM tasks WHERE date = ? ORDER BY time", (_today,)).fetchall()
            _conn.close()
            return {"date": _today, "tasks": [dict(_r) for _r in _rows]}

        @web_app.post("/api/tasks")
        async def create_task(title: str = "", date: str = "", time: str = "", task_type: str = "user"):
            import sqlite3 as _sqlite3, uuid as _uuid
            from datetime import datetime as _dt
            import os as _os; _db = _os.path.expanduser("~/.xiaobo-agent/memory.db")
            _conn = _sqlite3.connect(_db, timeout=10)
            _tid = "task-" + str(_uuid.uuid4())[:8]
            _conn.execute("INSERT INTO tasks (id, title, date, time, status, type, created_at) VALUES (?, ?, ?, ?, 'pending', ?, ?)",
                         (_tid, title, date, time, task_type, _dt.now().isoformat()))
            _conn.commit(); _conn.close()
            return {"id": _tid, "status": "created"}

        @web_app.put("/api/tasks/{task_id}/status")
        async def update_task_status(task_id: str, status: str = "done"):
            import sqlite3 as _sqlite3
            import os as _os; _db = _os.path.expanduser("~/.xiaobo-agent/memory.db")
            _conn = _sqlite3.connect(_db, timeout=10)
            _conn.execute("UPDATE tasks SET status = ? WHERE id = ?", (status, task_id))
            _conn.commit(); _conn.close()
            return {"status": "updated"}

        @web_app.get("/api/tasks/upcoming")
        async def get_upcoming_tasks():
            import sqlite3 as _sqlite3
            from datetime import datetime as _dt, timedelta as _td
            import os as _os; _db = _os.path.expanduser("~/.xiaobo-agent/memory.db")
            _conn = _sqlite3.connect(_db, timeout=10)
            _conn.row_factory = _sqlite3.Row
            _tomorrow = (_dt.now() + _td(days=1)).strftime("%Y-%m-%d")
            _rows = _conn.execute(
                "SELECT * FROM tasks WHERE date >= ? AND status = 'pending' AND time != '' AND time IS NOT NULL ORDER BY date, time",
                (_tomorrow,)
            ).fetchall()
            _conn.close()
            return {"tasks": [dict(_r) for _r in _rows]}

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
            
            # 处理特殊命令
            content = msg.content.strip()
            if content == "日报":
                report = await daily_report.generate_daily_report()
                await feishu_conn.broadcast(msg.chat_id, f"📋 今日日报\n\n{report}")
            elif content == "周报":
                report = await report_gen.generate_weekly_report()
                await feishu_conn.broadcast(msg.chat_id, f"📋 周报\n\n{report}")
            elif content == "月报":
                report = await report_gen.generate_monthly_report()
                await feishu_conn.broadcast(msg.chat_id, f"📋 月报\n\n{report}")
            elif content == "情绪":
                summary = await tracker.get_emotion_summary(days=7)
                await feishu_conn.broadcast(msg.chat_id, f"🎭 情绪摘要\n\n{summary}")
            elif content == "模式":
                pattern = await analyzer.analyze_weekly_pattern()
                text = f"📊 本周模式\n总消息: {pattern['total_messages']}\n最忙: {pattern['busiest_day']}\n最闲: {pattern['quietest_day']}"
                await feishu_conn.broadcast(msg.chat_id, text)
            elif content == "统计":
                stats = await memory.get_stats()
                await feishu_conn.broadcast(msg.chat_id, f"📊 记忆统计: {stats}")
            else:
                # 先检测任务列表（在LLM回复前，确保任务状态已更新）
                _detect_task_list(content)
                
                response = await handler.handle_message(content)
                await feishu_conn.broadcast(msg.chat_id, response)
                # 检测任务完成
                _detect_task_completion(content)
                _detect_task_completion(response)
            
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
                        # 先检测任务列表（在LLM回复前，确保任务状态已更新）
                        _detect_task_list(msg.content)
                        
                        response = await handler.handle_message(msg.content)
                        await wechat_conn.broadcast(msg.sender_id, response)
                        # 检测任务完成
                        _detect_task_completion(msg.content)
                        _detect_task_completion(response)

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
