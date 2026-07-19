# 📱 小柏手机监控 App

监控手机屏幕使用时间，自动上报到小柏 Agent 服务器。

## 功能
- 📊 实时显示今日屏幕使用时间
- 📋 展示 Top 5 最常用 App
- 🔄 每30分钟自动上报到服务器
- 🔔 通知栏常驻监控
- ✋ 一键手动上报

## 编译 APK（无需 Android Studio）

本项目已配置 **GitHub Actions**，推送到 GitHub 后会自动编译：

1. 在 GitHub 创建新仓库（如 `xiaobo-phone`）
2. 上传代码：
   ```bash
   cd android-app
   git init
   git add .
   git commit -m "init: 小柏手机监控 v1.0"
   git remote add origin git@github.com:你的用户名/xiaobo-phone.git
   git push -u origin main
   ```
3. 打开仓库 → **Actions** 标签 → 等待编译完成
4. 点击 **build** → 底部 **Artifacts** 下载 APK

## 安装到手机

1. 手机安装下载的 APK
2. 首次打开授予**使用情况访问权限**
3. 点击「启动服务」开始监控

## Vivo 手机后台保活设置

1. 设置 → 应用与权限 → 小柏监控 → 权限管理 → 允许后台运行
2. i管家 → 应用管理 → 小柏监控 → 允许自启动
3. 设置 → 电池 → 后台高耗电 → 小柏监控 → 允许
4. 多任务界面长按小柏监控 → 锁定

## 服务器配置

App 默认连接 `http://1.117.61.172:8088/api/phone/stats`。
如需修改，编辑 `MainActivity.kt` 中的 `SERVER_URL` 常量。
