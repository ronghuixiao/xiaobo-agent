"""Web Dashboard 路由

提供 Web 界面浏览记忆、情绪、报告等。
"""
import json
import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

logger = logging.getLogger(__name__)

# HTML 模板目录
TEMPLATE_DIR = Path(__file__).parent / "templates"

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>小柏 Agent - Dashboard</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f5; color: #333; }
.container { max-width: 900px; margin: 0 auto; padding: 20px; }
h1 { color: #2d3748; margin-bottom: 20px; }
h2 { color: #4a5568; margin: 20px 0 10px; font-size: 1.2em; }
.card { background: white; border-radius: 12px; padding: 20px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
.stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.stat-item { text-align: center; padding: 16px; background: #f7fafc; border-radius: 8px; }
.stat-number { font-size: 2em; font-weight: bold; color: #667eea; }
.stat-label { color: #718096; margin-top: 4px; }
.emotion-bar { display: flex; align-items: center; margin: 8px 0; }
.emotion-label { width: 80px; font-weight: 500; }
.emotion-fill { height: 24px; border-radius: 12px; background: #667eea; transition: width 0.3s; display: flex; align-items: center; padding-left: 8px; color: white; font-size: 0.85em; }
.btn { padding: 8px 16px; border: none; border-radius: 8px; cursor: pointer; font-size: 0.9em; margin-right: 8px; }
.btn-primary { background: #667eea; color: white; }
.btn-primary:hover { background: #5a67d8; }
.message-list { max-height: 400px; overflow-y: auto; }
.message { padding: 12px; margin: 8px 0; border-radius: 8px; }
.message.user { background: #edf2f7; }
.message.assistant { background: #ebf8ff; }
.message .role { font-weight: bold; font-size: 0.85em; color: #718096; }
.message .content { margin-top: 4px; }
.empty { text-align: center; color: #a0aec0; padding: 40px; }
</style>
</head>
<body>
<div class="container">
<h1>🌟 小柏 Agent Dashboard</h1>

<div class="card">
<h2>📊 记忆统计</h2>
<div class="stats-grid" id="stats">
  <div class="stat-item"><div class="stat-number" id="conversations">-</div><div class="stat-label">对话</div></div>
  <div class="stat-item"><div class="stat-number" id="facts">-</div><div class="stat-label">事实</div></div>
  <div class="stat-item"><div class="stat-number" id="emotions">-</div><div class="stat-label">情绪</div></div>
  <div class="stat-item"><div class="stat-number" id="associations">-</div><div class="stat-label">关联</div></div>
</div>
</div>

<div class="card">
<h2>🎭 情绪摘要（近7天）</h2>
<div id="emotion-summary"><div class="empty">加载中...</div></div>
</div>

<div class="card">
<h2>💬 最近对话</h2>
<div class="message-list" id="messages"><div class="empty">加载中...</div></div>
</div>

<div class="card">
<h2>📱 手机使用</h2>
<div id="phone-stats"><div class="empty">暂无数据</div></div>
</div>
</div>

<script>
async function loadStats() {
  try {
    const resp = await fetch('/api/stats');
    const data = await resp.json();
    document.getElementById('conversations').textContent = data.conversations || 0;
    document.getElementById('facts').textContent = data.facts || 0;
    document.getElementById('emotions').textContent = data.emotions || 0;
    document.getElementById('associations').textContent = data.associations || 0;
  } catch(e) { console.error('Stats load failed:', e); }
}

async function loadEmotions() {
  try {
    const resp = await fetch('/api/emotions/summary?days=7');
    const text = await resp.text();
    document.getElementById('emotion-summary').innerHTML = '<pre style="white-space:pre-wrap">' + text + '</pre>';
  } catch(e) { document.getElementById('emotion-summary').innerHTML = '<div class="empty">暂无情绪数据</div>'; }
}

async function loadPhoneStats() {
  try {
    const resp = await fetch('/api/phone/summary');
    const data = await resp.json();
    if (data.record_count > 0) {
      const hours = Math.floor(data.total_screen_time / 3600);
      const mins = Math.floor((data.total_screen_time % 3600) / 60);
      let html = '<p>今日屏幕时间: ' + hours + 'h ' + mins + 'm</p>';
      if (data.app_breakdown.length > 0) {
        html += '<ul>';
        data.app_breakdown.forEach(app => {
          const m = Math.floor(app.duration / 60);
          html += '<li>' + app.name + ': ' + m + '分钟</li>';
        });
        html += '</ul>';
      }
      document.getElementById('phone-stats').innerHTML = html;
    }
  } catch(e) {}
}

loadStats();
loadEmotions();
loadPhoneStats();
</script>
</body>
</html>"""


def create_dashboard_router() -> APIRouter:
    """创建 Dashboard 路由"""
    router = APIRouter(tags=["dashboard"])

    @router.get("/dashboard", response_class=HTMLResponse)
    async def dashboard():
        """Dashboard 页面"""
        return DASHBOARD_HTML

    return router
