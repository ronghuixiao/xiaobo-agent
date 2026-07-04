# TODO — 小柏 Agent (xiaobo-agent)

## Phase 0: 初始化
- [x] 0.1 项目骨架
- [x] 0.2 依赖管理 (pyproject.toml)
- [x] 0.3 配置文件 (config/)
- [x] 0.4 模块实现
- [x] 0.5 测试框架 (tests/)
- [x] 0.6 入口脚本 (main.py)
- [x] 0.7 TODO.md
- [x] 0.8 环境验证

## Phase 1: 核心记忆 + 对话 ✅
- [x] 1.1 LLM Provider (Ollama + OpenAI 兼容)
- [x] 1.2 分层记忆数据库 (SQLite)
- [x] 1.3 对话处理器 (ConversationHandler)
- [x] 1.4 信息抽取器 (MessageExtractor)
- [x] 1.5 微信连接层 (iLink Bot API)
- [x] 1.6 端到端测试 (25 passed)

## Phase 2: 情绪追踪 + 日报 + 语义检索 ✅
- [x] 2.1 情绪追踪模块 (EmotionTracker)
- [x] 2.2 历史对话语义检索 (SemanticSearch)
- [x] 2.3 每日报告生成 (DailyReportGenerator)
- [x] 2.4 定时推送 (CronScheduler)
- [x] 2.5 端到端测试 (33 passed)

## Phase 3: 感知 + 主动干预 ✅ ← 当前
- [x] 3.1 手机监控数据模型 (tests/test_phone_monitor.py)
- [x] 3.2 手机监控 API 端点 (src/api/phone.py + tests/test_phone_api.py)
- [x] 3.3 主动提醒引擎 (src/companion/proactive.py + tests/test_proactive.py)
- [x] 3.4 周报/月报生成 (src/companion/report_generator.py + tests/test_report_generator.py)
- [x] 3.5 模式分析器 (src/companion/pattern_analyzer.py + tests/test_pattern_analyzer.py)
- [x] 3.6 完整守护模式 (main.py --daemon)
- [x] 3.7 Web Dashboard (src/dashboard/app.py + tests/test_dashboard.py)
- [x] 3.8 微信 iLink 连接集成
- [x] 3.9 服务器部署 (deploy/)
- [x] 3.10 手机操作指南 (docs/PHONE_SETUP_GUIDE.md)

## Phase 4: 高级功能 (远期)
- [ ] 4.1 多模态支持（图片/语音）
- [ ] 4.2 多用户支持
- [ ] 4.3 插件系统
- [ ] 4.4 Docker Compose 部署

---

### Phase 3 功能详解

#### 3.1 手机监控 API
- `POST /api/phone/stats` — 接收手机上报数据
- `GET /api/phone/summary` — 获取今日使用摘要
- `GET /api/phone/daily?days=7` — 获取每日统计

#### 3.2 主动提醒引擎
规则：
- `mood_check` — 情绪低落时主动关心（12h 冷却）
- `long_silence` — 长时间未聊时问候（48h 冷却）
- `screen_time_exceeded` — 屏幕时间超标提醒（4h 冷却）
- `daily_check_in` — 每日早安签到（20h 冷却）

#### 3.3 报告生成
- 日报：`python main.py` 交互模式输入 `report`
- 周报：输入 `week`
- 月报：输入 `month`
- 守护模式：每天 22:00 自动推送日报到微信

#### 3.4 模式分析
- 行为规律分析（哪天最忙、最闲）
- 情绪预测（基于历史同星期数据）
- 活动热力图（7x24 矩阵）
- 习惯变化检测

---

*最后更新: 2026-07-05*
*测试状态: 55/55 passed (49 unit + 6 dashboard)*
