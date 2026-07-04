# 📱 手机监控配置指南

> 让小柏能感知你的手机使用习惯，提供主动关怀。

---

## 方案一：Tasker + HTTP POST（推荐 ⭐⭐⭐⭐）

**最简单可靠的方案**，无需 root，无需编程。

### 前置条件
- Android 手机
- Tasker App（Google Play，付费约 ¥25）
- 手机和服务器在同一网络（或服务器有公网 IP）

### Step 1: 安装 Tasker

1. 打开 Google Play
2. 搜索 **Tasker**（开发者: joaomgcd）
3. 购买并安装（约 ¥25）
4. 首次打开时允许所有权限

### Step 2: 获取屏幕使用时间

**方案 A: 使用 Tasker 内置功能**
1. Tasker → 搜索 "UsageStats"
2. 如果手机有 UsageStatsManager 权限，直接读取

**方案 B: 使用 AutoNotification 插件**（免费）
1. 安装 **AutoNotification**（免费版即可）
2. AutoNotification → Enable → 允许通知使用权
3. 通过通知获取使用时间

### Step 3: 创建 Tasker 任务

1. 打开 Tasker → **Tasks** 标签 → **+** 创建新任务
2. 命名为 **"手机数据上报"**

**添加 Action 1: HTTP Request**
- 点击 **+** → Net → HTTP Request
- Method: **POST**
- URL: `http://你的服务器IP:8088/api/phone/stats`
- Body:
```json
{
  "device_id": "android_ronghui",
  "timestamp": "%DATE %TIME",
  "screen_time_total": 0,
  "app_usages": []
}
```
- Content Type: `application/json`

**添加 Action 2: 获取使用时间**（简化版）
- 点击 **+** → App → App Info
- 获取当前前台 App 信息

### Step 4: 设置定时触发

1. 打开 Tasker → **Profiles** 标签 → **+** 创建新 Profile
2. 选择 **Time** → Every **30 分钟**
3. 关联上面创建的 **"手机数据上报"** 任务
4. 保存

### Step 5: 验证

1. 手动运行一次任务
2. 在服务器上检查：
```bash
curl http://localhost:8088/api/phone/summary
```
3. 应该返回数据

---

## 方案二：Termux + 脚本（免费 ⭐⭐⭐）

**完全免费**，但需要一些命令行知识。

### Step 1: 安装 Termux

> ⚠️ **必须从 F-Droid 安装**，Google Play 版本已过期

1. 下载 F-Droid：https://f-droid.org/
2. 在 F-Droid 中搜索 **Termux** 并安装
3. 同时安装 **Termux:API** 插件

### Step 2: 安装依赖

打开 Termux，运行：
```bash
pkg update
pkg install termux-api python curl jq
```

### Step 3: 创建上报脚本

```bash
mkdir -p ~/xiaobo-report
cat > ~/xiaobo-report/report.sh << 'EOF'
#!/bin/bash
# 小柏手机数据上报脚本

SERVER="http://你的服务器IP:8088"
DEVICE_ID="android_ronghui"

# 获取屏幕使用时间（需要 Termux:API）
SCREEN_TIME=$(termux-notification-list | wc -l)

# 构建 JSON
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%S")
JSON=$(cat << ENDJSON
{
  "device_id": "$DEVICE_ID",
  "timestamp": "$TIMESTAMP",
  "screen_time_total": 0,
  "app_usages": []
}
ENDJSON
)

# 上报
curl -s -X POST "$SERVER/api/phone/stats" \
  -H "Content-Type: application/json" \
  -d "$JSON"
EOF
chmod +x ~/xiaobo-report/report.sh
```

### Step 4: 设置定时执行

```bash
# 每 30 分钟执行一次
crontab -e
# 添加这行：
*/30 * * * * ~/xiaobo-report/report.sh >> /tmp/xiaobo-report.log 2>&1
```

---

## 方案三：Android App（开发中）

未来会提供一个专用的 Android App，自动采集：
- 屏幕使用时间
- 各 App 使用时长
- 前台 App 切换记录

敬请期待。

---

## 数据格式说明

### POST /api/phone/stats

```json
{
  "device_id": "android_ronghui",     // 设备标识
  "timestamp": "2026-07-05T22:00:00", // 上报时间
  "screen_time_total": 18000,         // 当日总亮屏时间（秒）
  "app_usages": [                     // 各 App 使用情况
    {
      "package": "com.ss.android.ugc.aweme",  // 包名
      "name": "抖音",                          // 显示名
      "duration": 3600                          // 使用时长（秒）
    },
    {
      "package": "com.tencent.mm",
      "name": "微信",
      "duration": 1800
    }
  ]
}
```

### 获取摘要

```bash
# 今日摘要
curl http://服务器IP:8088/api/phone/summary

# 过去 7 天
curl http://服务器IP:8088/api/phone/daily?days=7
```

---

## 常见问题

### Q: Tasker 很贵，有免费方案吗？
A: 用方案二（Termux），完全免费。

### Q: 手机不在同一网络怎么办？
A: 服务器有公网 IP 就行，手机用移动数据也能上报。

### Q: 上报数据安全吗？
A: 数据存在你的服务器上，不会发到第三方。建议后续添加 API Key 认证。

### Q: 能自动获取各 App 使用时间吗？
A: 需要 Android 的 UsageStatsManager 权限，Tasker 有插件支持。

### Q: 手机电量消耗大吗？
A: 每 30 分钟一次 HTTP POST，几乎无电量消耗。
