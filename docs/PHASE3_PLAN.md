# Phase 3 架构规划 — 感知 + 主动干预

> 本文档规划 Phase 3 的实现方向，包含代码预留和接口设计。
> Phase 3 尚未实施，仅供参考后续开发。

---

## 概览

Phase 3 的核心目标：让小柏从"被动响应"进化为"主动感知+主动干预"。

```
Phase 1: 你说，我记        ✅ 已完成
Phase 2: 我总结，我提醒    ✅ 已完成
Phase 3: 我感知，我主动    📋 规划中
```

---

## 模块 3.1: 手机使用监控接口

### 架构设计

```
┌─────────────────────┐
│   Android App /     │
│   Tasker 脚本       │  ← 采集手机使用数据
└─────────┬───────────┘
          │ HTTP POST
          ▼
┌─────────────────────┐
│  /api/phone-stats   │  ← FastAPI 接收端点
│  (xiaobo-agent)     │
└─────────┬───────────┘
          │ 解析 + 存储
          ▼
┌─────────────────────┐
│  phone_usage 表     │  ← SQLite 存储
│  (MemoryDatabase)   │
└─────────┬───────────┘
          │ 分析
          ▼
┌─────────────────────┐
│  PhoneMonitor       │  ← 异常检测 + 阈值告警
│  (companion/)       │
└─────────────────────┘
```

### 数据模型预留

```python
# src/memory/base.py 预留

@dataclass
class PhoneUsageRecord:
    """手机使用记录"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    device_id: str = ""
    app_package: str = ""      # com.ss.android.ugc.aweme (抖音)
    app_name: str = ""
    duration_seconds: int = 0  # 使用时长
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    screen_time_total: int = 0 # 当日总亮屏时间
```

### API 端点预留

```python
# src/api/phone.py 预留

@router.post("/api/phone/stats")
async def receive_phone_stats(stats: PhoneStatsPayload):
    """接收手机统计数据"""
    ...

@router.get("/api/phone/summary")
async def get_phone_summary(date: str = None):
    """获取手机使用摘要"""
    ...
```

### Android 端数据采集方案

| 方案 | 原理 | 需要权限 | 推荐度 |
|------|------|----------|--------|
| UsageStatsManager | 系统 API 读取使用统计 | PACKAGE_USAGE_STATS | ⭐⭐⭐⭐ |
| Accessibility Service | 监听前台应用切换 | 无障碍服务 | ⭐⭐⭐ |
| Tasker + HTTP | Tasker 定时上报 | 通知使用权 | ⭐⭐⭐⭐ |
| Termux + 脚本 | 在手机上跑脚本 | 无特殊权限 | ⭐⭐ |

**推荐：Tasker + HTTP POST**（最快落地）

---

## 模块 3.2: 主动提醒系统

### 架构设计

```
┌─────────────────┐
│ CronScheduler   │  ← 定时检查
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ ProactiveEngine │  ← 决策引擎
│                 │
│ 规则 1: 连续刷抖音 > 1h → 提醒
│ 规则 2: 到任务时间 → 提醒
│ 规则 3: 情绪低落 → 安慰
│ 规则 4: 长时间不聊 → 关心
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ WeChat.push()   │  ← 微信推送
└─────────────────┘
```

### 主动提醒规则预留

```python
# src/companion/proactive.py 预留

class ProactiveRule:
    """主动提醒规则"""
    name: str
    condition: Callable  # 判断条件
    message: str         # 提醒内容模板
    cooldown: int        # 冷却时间（秒）

class ProactiveEngine:
    """主动干预引擎"""
    rules: List[ProactiveRule]

    async def check(self, context: Dict) -> List[str]:
        """检查所有规则，返回需要发送的提醒"""
        ...

    # 预定义规则:
    # 1. screen_time_exceeded: 屏幕时间超标
    # 2. entertainment_overuse: 娱乐App使用过久
    # 3. task_reminder: 任务到期提醒
    # 4. mood_check: 情绪低落关心
    # 5. daily_check_in: 每日签到
```

---

## 模块 3.3: 周报/月报生成

### 数据聚合

```python
# src/companion/report_generator.py 预留

class ReportGenerator:
    """报告生成器（日报/周报/月报）"""

    async def generate_daily_report(self, date: datetime) -> str:
        """日报 - 已实现"""
        ...

    async def generate_weekly_report(self, week_start: datetime) -> str:
        """周报 - 包含：对话回顾、情绪趋势、任务完成率、手机使用"""
        ...

    async def generate_monthly_report(self, month: int, year: int) -> str:
        """月报 - 包含：成长轨迹、习惯变化、目标进展"""
        ...
```

### 周报模板预留

```markdown
# 荣慧的周报 — 2026年第27周

## 📊 本周概览
- 对话: XX 条 | 活跃: X 天
- 情绪: 😊X% 😢X% 😰X% 
- 手机: 日均 Xh

## 🎯 任务完成
- [x] 刷LeetCode 50题
- [x] 读论文2篇
- [ ] 学Rust（未开始）

## 🎭 情绪趋势
周初 😰焦虑 → 周中 😊平稳 → 周末 😢低落

## 📱 手机使用
- 日均屏幕时间: 4.5h
- 抖音: 日均 1.2h (比上周减少20min)
- LeetCode: 日均 45min

## 💡 小柏的话
你这周LeetCode坚持得不错，情绪周末有点波动，记得和朋友聊聊天。
```

---

## 模块 3.4: 跨周模式分析

### 设计思路

```python
# src/companion/pattern_analyzer.py 预留

class PatternAnalyzer:
    """模式分析器"""

    async def analyze_weekly_pattern(self) -> Dict:
        """分析每周模式：哪天最忙、哪天最闲、情绪规律"""
        ...

    async def detect_habit_changes(self) -> List[str]:
        """检测习惯变化：使用时间增减、新偏好出现"""
        ...

    async def predict_mood(self) -> Dict:
        """基于历史模式预测今日情绪"""
        ...
```

---

## 模块 3.5: Web Dashboard

### 技术选型

| 方案 | 优点 | 缺点 |
|------|------|------|
| FastAPI + Jinja2 | 简单，后端直出 | 交互性差 |
| React + Vite | 交互好，现代 | 开发量大 |
| Gradio | 快速原型 | 不够美观 |
| Streamlit | 快速原型 | 性能一般 |

**推荐：FastAPI + 简单 HTML**（Phase 3 初期用，后续按需升级）

### Dashboard 页面预留

```
/dashboard
├── /today          # 今日概览（对话、情绪、手机使用）
├── /memory         # 记忆浏览（搜索、按类型筛选）
├── /emotions       # 情绪时间线（图表）
├── /reports        # 历史报告（日报/周报/月报）
└── /settings       # 配置（提醒规则、LLM切换等）
```

---

## 实施优先级

| 优先级 | 模块 | 预估工作量 | 依赖 |
|--------|------|-----------|------|
| P0 | 手机监控接口 | 2天 | Android端 |
| P0 | 主动提醒（基础版） | 1天 | 手机监控 |
| P1 | 周报/月报 | 1天 | 日报 |
| P1 | 跨周模式分析 | 2天 | 足够数据 |
| P2 | Web Dashboard | 3天 | 无 |

---

## 代码预留文件

```
src/
├── api/                    # API 端点（Phase 3）
│   ├── __init__.py
│   └── phone.py           # 手机数据接收端点
├── companion/
│   ├── proactive.py       # 主动提醒引擎
│   ├── pattern_analyzer.py # 模式分析
│   └── report_generator.py # 周报/月报
└── dashboard/             # Web Dashboard
    ├── __init__.py
    └── templates/         # HTML 模板
```

---

*文档创建时间: 2026-07-03*
*最后更新: 2026-07-03*
