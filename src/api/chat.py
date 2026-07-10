"""Web 聊天 API 端点

提供 Web 聊天功能，与微信共享同一套对话记忆。
- POST /api/chat — 发送消息，获取回复
- GET /api/chat/history — 获取对话历史
- GET /chat — 聊天页面
"""
import json
import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    """聊天请求"""
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    """聊天响应"""
    reply: str
    session_id: str


# 全局引用（由 main.py 注入）
_handler = None
_memory = None


def init_chat(handler, memory):
    """初始化聊天模块的依赖引用"""
    global _handler, _memory
    _handler = handler
    _memory = memory


CHAT_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>小柏 - 聊天</title>
<style>
:root {
  --primary: #667eea;
  --primary-dark: #5a67d8;
  --bg: #f7f8fc;
  --card: #ffffff;
  --text: #2d3748;
  --text-secondary: #718096;
  --border: #e2e8f0;
  --user-bubble: #667eea;
  --user-text: #ffffff;
  --bot-bubble: #ffffff;
  --bot-text: #2d3748;
  --shadow: 0 2px 12px rgba(0,0,0,0.08);
}
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { height: 100%; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', sans-serif;
  background: var(--bg);
  color: var(--text);
  display: flex;
  flex-direction: column;
  height: 100%;
}

/* Header */
.header {
  background: var(--card);
  border-bottom: 1px solid var(--border);
  padding: 14px 20px;
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
  box-shadow: 0 1px 4px rgba(0,0,0,0.04);
  z-index: 10;
}
.header-avatar {
  width: 40px; height: 40px;
  border-radius: 50%;
  background: linear-gradient(135deg, #667eea, #764ba2);
  display: flex; align-items: center; justify-content: center;
  font-size: 20px; color: white; flex-shrink: 0;
}
.header-info h1 { font-size: 16px; font-weight: 600; }
.header-info p { font-size: 12px; color: var(--text-secondary); margin-top: 2px; }
.header-status {
  margin-left: auto;
  display: flex; align-items: center; gap: 6px;
  font-size: 12px; color: #48bb78;
}
.status-dot {
  width: 8px; height: 8px; border-radius: 50%; background: #48bb78;
  animation: pulse 2s infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* Chat Area */
.chat-area {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  scroll-behavior: smooth;
  -webkit-overflow-scrolling: touch;
}

/* Welcome */
.welcome {
  text-align: center;
  padding: 40px 20px;
  color: var(--text-secondary);
}
.welcome-avatar {
  width: 72px; height: 72px;
  border-radius: 50%;
  background: linear-gradient(135deg, #667eea, #764ba2);
  display: flex; align-items: center; justify-content: center;
  font-size: 36px; color: white;
  margin: 0 auto 16px;
}
.welcome h2 { font-size: 20px; color: var(--text); margin-bottom: 8px; }
.welcome p { font-size: 14px; line-height: 1.6; }
.quick-actions {
  display: flex; flex-wrap: wrap; gap: 8px;
  justify-content: center; margin-top: 20px;
}
.quick-btn {
  padding: 8px 16px; border-radius: 20px;
  border: 1px solid var(--border); background: var(--card);
  font-size: 13px; color: var(--text); cursor: pointer;
  transition: all 0.2s;
}
.quick-btn:hover { border-color: var(--primary); color: var(--primary); background: #f0f0ff; }

/* Messages */
.message {
  display: flex;
  gap: 10px;
  max-width: 85%;
  animation: fadeIn 0.3s ease;
}
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
.message.user {
  align-self: flex-end;
  flex-direction: row-reverse;
}
.message.assistant {
  align-self: flex-start;
}
.msg-avatar {
  width: 34px; height: 34px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 16px; color: white; flex-shrink: 0;
  margin-top: 2px;
}
.message.user .msg-avatar {
  background: linear-gradient(135deg, #667eea, #764ba2);
}
.message.assistant .msg-avatar {
  background: linear-gradient(135deg, #48bb78, #38a169);
}
.msg-bubble {
  padding: 12px 16px;
  border-radius: 18px;
  line-height: 1.6;
  font-size: 14px;
  word-break: break-word;
  white-space: pre-wrap;
}
.message.user .msg-bubble {
  background: var(--user-bubble);
  color: var(--user-text);
  border-bottom-right-radius: 4px;
}
.message.assistant .msg-bubble {
  background: var(--bot-bubble);
  color: var(--bot-text);
  border-bottom-left-radius: 4px;
  box-shadow: var(--shadow);
}
.msg-time {
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 4px;
  text-align: right;
}
.message.assistant .msg-time {
  text-align: left;
}

/* Typing indicator */
.typing {
  display: flex; gap: 4px; padding: 12px 16px;
  align-items: center;
}
.typing-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: #a0aec0;
  animation: typingBounce 1.4s infinite;
}
.typing-dot:nth-child(2) { animation-delay: 0.2s; }
.typing-dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes typingBounce {
  0%, 60%, 100% { transform: translateY(0); }
  30% { transform: translateY(-6px); }
}

/* Input Area */
.input-area {
  background: var(--card);
  border-top: 1px solid var(--border);
  padding: 12px 16px;
  flex-shrink: 0;
  padding-bottom: max(12px, env(safe-area-inset-bottom));
}
.input-wrapper {
  display: flex;
  gap: 10px;
  align-items: flex-end;
  max-width: 800px;
  margin: 0 auto;
}
#msg-input {
  flex: 1;
  border: 1px solid var(--border);
  border-radius: 22px;
  padding: 10px 18px;
  font-size: 15px;
  font-family: inherit;
  resize: none;
  outline: none;
  max-height: 120px;
  min-height: 44px;
  line-height: 1.4;
  transition: border-color 0.2s;
  background: var(--bg);
}
#msg-input:focus { border-color: var(--primary); }
#send-btn {
  width: 44px; height: 44px;
  border-radius: 50%;
  border: none;
  background: var(--primary);
  color: white;
  font-size: 18px;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: all 0.2s;
  flex-shrink: 0;
}
#send-btn:hover { background: var(--primary-dark); transform: scale(1.05); }
#send-btn:disabled { background: #cbd5e0; cursor: not-allowed; transform: none; }

/* Error toast */
.toast {
  position: fixed; top: 20px; left: 50%; transform: translateX(-50%);
  background: #e53e3e; color: white;
  padding: 10px 20px; border-radius: 8px;
  font-size: 13px; z-index: 100;
  opacity: 0; transition: opacity 0.3s;
  pointer-events: none;
}
.toast.show { opacity: 1; }

/* Desktop wider */
@media (min-width: 768px) {
  .chat-area { padding: 24px; }
  .message { max-width: 70%; }
}
</style>
</head>
<body>

<div class="header">
  <div class="header-avatar">🌟</div>
  <div class="header-info">
    <h1>小柏</h1>
    <p>你的个人数字伙伴</p>
  </div>
  <div class="header-status">
    <div class="status-dot"></div>
    <span>在线</span>
  </div>
</div>

<div class="chat-area" id="chat-area">
  <div class="welcome" id="welcome">
    <div class="welcome-avatar">🌟</div>
    <h2>你好，我是小柏</h2>
    <p>你的个人数字伙伴，帮你记住你、理解你。<br>和我聊聊吧，我会记住你说的每一件事。</p>
    <div class="quick-actions">
      <div class="quick-btn" onclick="sendQuick('今天心情不错')">😊 今天心情不错</div>
      <div class="quick-btn" onclick="sendQuick('帮我记录一件事')">📝 记录一件事</div>
      <div class="quick-btn" onclick="sendQuick('最近有什么提醒')">⏰ 最近提醒</div>
      <div class="quick-btn" onclick="sendQuick('统计')">📊 记忆统计</div>
    </div>
  </div>
</div>

<div class="input-area">
  <div class="input-wrapper">
    <textarea id="msg-input" rows="1" placeholder="输入消息..." 
      oninput="autoResize(this)" onkeydown="handleKey(event)"></textarea>
    <button id="send-btn" onclick="sendMessage()">➤</button>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
const chatArea = document.getElementById('chat-area');
const msgInput = document.getElementById('msg-input');
const sendBtn = document.getElementById('send-btn');
const toast = document.getElementById('toast');

let sessionId = localStorage.getItem('xiaobo_session_id') || null;
let isWaiting = false;

// Auto-resize textarea
function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 120) + 'px';
}

// Enter to send, Shift+Enter for newline
function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
}

// Quick action
function sendQuick(text) {
  msgInput.value = text;
  sendMessage();
}

// Show/hide welcome
function hideWelcome() {
  const w = document.getElementById('welcome');
  if (w) w.style.display = 'none';
}

// Format message content (handle line breaks)
function formatMessage(content) {
  return escapeHtml(content).replace(/\n/g, '<br>');
}

// Add message to chat
function addMessage(role, content, time) {
  hideWelcome();
  
  const div = document.createElement('div');
  div.className = 'message ' + role;
  
  const avatar = role === 'user' ? '👤' : '🌟';
  const timeStr = time || new Date().toLocaleTimeString('zh-CN', {hour:'2-digit', minute:'2-digit'});
  
  div.innerHTML = `
    <div class="msg-avatar">${avatar}</div>
    <div>
      <div class="msg-bubble">${escapeHtml(content)}</div>
      <div class="msg-time">${timeStr}</div>
    </div>
  `;
  chatArea.appendChild(div);
  scrollToBottom();
  return div;
}

// Typing indicator
function showTyping() {
  const div = document.createElement('div');
  div.className = 'message assistant';
  div.id = 'typing-indicator';
  div.innerHTML = `
    <div class="msg-avatar">🌟</div>
    <div class="msg-bubble">
      <div class="typing">
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
      </div>
    </div>
  `;
  chatArea.appendChild(div);
  scrollToBottom();
}

function hideTyping() {
  const t = document.getElementById('typing-indicator');
  if (t) t.remove();
}

// Send message
async function sendMessage() {
  const text = msgInput.value.trim();
  if (!text || isWaiting) return;
  
  isWaiting = true;
  sendBtn.disabled = true;
  msgInput.value = '';
  autoResize(msgInput);
  
  addMessage('user', text);
  
  // 创建助手消息容器（用于流式输出）
  const assistantDiv = document.createElement('div');
  assistantDiv.className = 'message assistant';
  assistantDiv.innerHTML = `
    <div class="msg-avatar">🤖</div>
    <div class="msg-content">
      <div class="msg-bubble" id="streaming-bubble">
        <div class="typing-indicator">
          <span></span><span></span><span></span>
        </div>
      </div>
    </div>
  `;
  chatArea.appendChild(assistantDiv);
  scrollToBottom();
  
  const streamingBubble = document.getElementById('streaming-bubble');
  let fullContent = '';
  
  try {
    const resp = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, session_id: sessionId })
    });
    
    if (!resp.ok) throw new Error('请求失败: ' + resp.status);
    
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      
      const chunk = decoder.decode(value);
      const lines = chunk.split('\n');
      
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6));
            
            if (data.type === 'session') {
              sessionId = data.session_id;
              localStorage.setItem('xiaobo_session_id', sessionId);
            } else if (data.type === 'chunk') {
              fullContent += data.content;
              streamingBubble.innerHTML = formatMessage(fullContent);
              scrollToBottom();
            } else if (data.type === 'done') {
              streamingBubble.removeAttribute('id');
            }
          } catch (e) {
            // ignore parse errors
          }
        }
      }
    }
  } catch (err) {
    streamingBubble.innerHTML = '<span style="color: #ef4444;">发送失败，请重试</span>';
    console.error(err);
  } finally {
    isWaiting = false;
    sendBtn.disabled = false;
    msgInput.focus();
  }
}

// Load history on page load
async function loadHistory() {
  try {
    const resp = await fetch('/api/chat/history?limit=30');
    if (!resp.ok) return;
    const data = await resp.json();
    
    if (data.messages && data.messages.length > 0) {
      hideWelcome();
      for (const msg of data.messages) {
        const time = new Date(msg.timestamp).toLocaleTimeString('zh-CN', {hour:'2-digit', minute:'2-digit'});
        addMessage(msg.role, msg.content, time);
      }
    }
  } catch (e) {
    // ignore
  }
}

// Helpers
function scrollToBottom() {
  requestAnimationFrame(() => {
    chatArea.scrollTop = chatArea.scrollHeight;
  });
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function showToast(msg) {
  toast.textContent = msg;
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 3000);
}

// Init
msgInput.focus();
loadHistory();
</script>
</body>
</html>"""


def create_chat_router() -> APIRouter:
    """创建聊天 API 路由"""
    router = APIRouter(tags=["chat"])

    @router.get("/chat", response_class=HTMLResponse)
    async def chat_page():
        """聊天页面"""
        return CHAT_HTML

    @router.post("/api/chat", response_model=ChatResponse)
    async def chat_send(req: ChatRequest):
        """发送消息并获取回复（非流式，兼容旧客户端）"""
        if not _handler:
            return {"error": "聊天模块未初始化"}, 500

        # 使用传入的 session_id 或创建新的
        if req.session_id:
            _handler._current_session_id = req.session_id
        else:
            _handler.start_session()

        reply = await _handler.handle_message(req.message)

        return ChatResponse(
            reply=reply,
            session_id=_handler._current_session_id,
        )

    @router.post("/api/chat/stream")
    async def chat_stream(req: ChatRequest):
        """发送消息并获取流式回复（SSE）"""
        from fastapi.responses import StreamingResponse
        
        if not _handler:
            return {"error": "聊天模块未初始化"}, 500

        # 使用传入的 session_id 或创建新的
        if req.session_id:
            _handler._current_session_id = req.session_id
        else:
            _handler.start_session()

        session_id = _handler._current_session_id

        async def event_generator():
            """SSE 事件生成器"""
            # 发送 session_id
            yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"
            
            # 流式生成回复
            async for chunk in _handler.stream_handle_message(req.message):
                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"
            
            # 发送完成信号
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @router.get("/api/chat/history")
    async def chat_history(limit: int = 30):
        """获取对话历史"""
        if not _memory:
            return {"messages": []}

        messages = await _memory.get_messages(limit=limit)
        return {
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    "timestamp": m.timestamp.isoformat(),
                    "session_id": m.session_id,
                }
                for m in messages
            ]
        }

    return router
