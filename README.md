# 小柏 (XiaoBo) - 个人数字伙伴

一个基于 LLM 的个人记忆伙伴，帮你记住你、理解你。

## 核心特性

- 🧠 **分层记忆系统** — 原始对话 / 提取事实 / 情绪追踪 / 关联索引
- 🔌 **多 LLM 支持** — Ollama (本地) / OpenAI / Mimo 等兼容 API
- 💬 **微信连接** — 基于 Hermes iLink Bot API，微信扫码即可连接
- 📊 **信息抽取** — 自动从对话中提取事实和情绪
- 📈 **情绪追踪** — 情绪时间线、趋势分析
- 🔍 **语义检索** — 向量嵌入相似度搜索
- 📋 **每日报告** — 日报/周报/月报自动生成
- 🔔 **主动提醒** — 情绪关怀、屏幕时间、每日签到
- 📱 **手机监控** — 接收 Android 使用数据，分析习惯
- 🌐 **Web Dashboard** — 浏览记忆、情绪、统计
- 💻 **Web 聊天** — 浏览器直接和小柏对话，与微信共享记忆

## 快速开始

```bash
# 安装依赖
pip install -e ".[dev]"
pip install fastapi uvicorn aiohttp jinja2

# 测试配置
python main.py --test

# 交互模式（终端对话）
python main.py

# 守护模式（微信 + 定时任务 + API）
python main.py --daemon

# Web API 模式
python main.py --web
```

### Web 聊天
```bash
# 启动后访问 http://服务器IP:8088/chat
python main.py --daemon
# 或
python main.py --web
```

浏览器打开 `/chat` 即可和小柏对话，微信和网页共享同一套对话记忆。

## 项目结构

```
xiaobo-agent/
├── src/
│   ├── llm/              # LLM Provider 抽象层
│   ├── memory/           # 分层记忆系统 + 语义检索
│   ├── companion/        # 对话 + 情绪 + 报告 + 主动提醒 + 模式分析
│   ├── wechat/           # 微信连接层 (iLink Bot API)
│   ├── api/              # FastAPI 端点 (手机监控 + Web 聊天)
│   │   ├── chat.py       # Web 聊天 API + 聊天页面
│   │   └── phone.py      # 手机监控端点
│   └── dashboard/        # Web Dashboard
├── tests/                # 测试 (55 个)
├── config/               # 配置管理
├── deploy/               # 服务器部署
├── docs/                 # 文档
├── main.py               # 主入口
└── TODO.md               # 任务追踪
```

## 运行模式

### 交互模式
```bash
python main.py
```
打开后终端聊天，内置命令：
- `stats` — 查看记忆统计
- `report` — 生成日报
- `week` — 生成周报
- `month` — 生成月报
- `mood` — 情绪摘要
- `pattern` — 行为分析

### 守护模式
```bash
python main.py --daemon
```
启动所有功能：
- ✅ 微信扫码连接
- ✅ 每天 22:00 日报推送
- ✅ 每天 08:00 早安签到
- ✅ 每 4 小时主动提醒检查
- ✅ Web API 服务 (端口 8088)

### 服务器部署
```bash
# 一键部署
bash deploy/start.sh

# 管理
systemctl status xiaobo-agent
systemctl restart xiaobo-agent
journalctl -u xiaobo-agent -f
```

## 记忆架构

| 层级 | 内容 | 存储 |
|------|------|------|
| Layer 0 | 原始对话存档 | SQLite 全量存储 |
| Layer 1 | 提取的事实 | 结构化存储，支持检索 |
| Layer 2 | 情绪时间线 | 情感维度记录 |
| Layer 3 | 关联索引 | 关键词 → 对话映射 |

## 主动提醒规则

| 规则 | 触发条件 | 冷却时间 |
|------|----------|----------|
| 🎭 情绪关怀 | 最近 24h 负面情绪 >60% | 12 小时 |
| 👋 长时间未聊 | 超过 48h 没聊天 | 48 小时 |
| 📱 屏幕时间 | 当日亮屏 >4 小时 | 4 小时 |
| ☀️ 早安签到 | 每天 8:00 | 20 小时 |

## 微信连接

守护模式下，小柏通过 iLink Bot API 连接微信：

1. 在 `config/config.yaml` 中配置 `wechat.ilink_token`
2. 运行 `python main.py --daemon`
3. 扫码登录微信
4. 小柏会自动回复消息，并在指定时间推送报告

**微信指令：**
- 发送 `日报` — 立即生成日报
- 发送 `周报` — 立即生成周报
- 发送 `月报` — 立即生成月报
- 发送 `情绪` — 查看情绪摘要
- 发送 `模式` — 查看行为分析
- 发送 `统计` — 查看记忆统计

## 手机监控

详见 [手机操作指南](docs/PHONE_SETUP_GUIDE.md)

**快速配置（Tasker 方案）：**
1. 安装 Tasker（Google Play，¥25）
2. 创建 HTTP POST 任务，发送到 `http://服务器IP:8088/api/phone/stats`
3. 设置每 30 分钟触发

## 测试

```bash
# 运行所有单元测试
PYTHONPATH=. pytest tests/ -v --ignore=tests/test_e2e.py --ignore=tests/test_e2e_phase2.py

# 运行端到端测试（需要 Ollama）
PYTHONPATH=. pytest tests/test_e2e.py tests/test_e2e_phase2.py -v
```

## 开发路线

- [x] Phase 1: 核心记忆 + 对话 (25 tests)
- [x] Phase 2: 情绪追踪 + 日报 + 语义检索 (33 tests)
- [x] Phase 3: 感知 + 主动干预 + 服务器部署 (55 tests)
- [ ] Phase 4: 多模态 + 多用户 + 插件系统

---

*最后更新: 2026-07-05*
*测试状态: 55/55 passed*
