#!/bin/bash
# 小柏 Agent 启动脚本

set -e

PROJECT_DIR="/root/xiaobo-agent"
SERVICE_NAME="xiaobo-agent"

echo "🌟 小柏 Agent 部署脚本"
echo "========================"

# 1. 安装依赖
echo "📦 安装依赖..."
cd "$PROJECT_DIR"
pip install -q fastapi uvicorn jinja2 aiohttp aiofiles 2>/dev/null || true

# 2. 创建配置文件（如果不存在）
if [ ! -f "$PROJECT_DIR/config/config.yaml" ]; then
    echo "📝 创建默认配置文件..."
    cp "$PROJECT_DIR/config/config.example.yaml" "$PROJECT_DIR/config/config.yaml"
    echo "⚠️  请编辑 config/config.yaml 填入微信 token 等配置"
fi

# 3. 创建 systemd service
echo "🔧 安装 systemd 服务..."
cp "$PROJECT_DIR/deploy/xiaobo-agent.service" /etc/systemd/system/
systemctl daemon-reload

# 4. 启动服务
echo "🚀 启动服务..."
systemctl enable "$SERVICE_NAME"
systemctl start "$SERVICE_NAME"

# 5. 检查状态
sleep 2
if systemctl is-active --quiet "$SERVICE_NAME"; then
    echo ""
    echo "✅ 小柏 Agent 已启动！"
    echo ""
    echo "📋 常用命令:"
    echo "   查看状态: systemctl status $SERVICE_NAME"
    echo "   查看日志: journalctl -u $SERVICE_NAME -f"
    echo "   重启:     systemctl restart $SERVICE_NAME"
    echo "   停止:     systemctl stop $SERVICE_NAME"
    echo ""
    echo "🌐 API 端点:"
    echo "   Dashboard: http://$(hostname -I | awk '{print $1}'):8088/dashboard"
    echo "   手机数据:  http://$(hostname -I | awk '{print $1}'):8088/api/phone/stats"
    echo "   统计信息:  http://$(hostname -I | awk '{print $1}'):8088/api/stats"
else
    echo "❌ 启动失败，请检查日志:"
    echo "   journalctl -u $SERVICE_NAME -n 20"
fi
