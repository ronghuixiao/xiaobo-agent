
---

### 问题23：对话输出体验差 - 改为流式输出

**现象**：
对话时小柏agent是整段输出，体验不好，希望能实时看到输出内容。

**根因分析**：
1. **当前实现是等待完整响应** - 前端发送POST请求，等待LLM生成完整回复后一次性显示
2. **没有流式输出支持** - LLM provider、handler、API都没有流式接口

**修复方案**：

1. **在LLM基类中添加stream_chat方法**（src/llm/base.py）
   ```python
   @abstractmethod
   async def stream_chat(
       self,
       messages: List[ChatMessage],
       temperature: Optional[float] = None,
       max_tokens: Optional[int] = None,
   ) -> AsyncGenerator[str, None]:
       """流式对话请求，逐token返回"""
       ...
   ```

2. **在OpenAI provider中实现stream_chat**（src/llm/openai_provider.py）
   - 使用OpenAI SDK的stream=True参数
   - 逐chunk返回内容

3. **在Ollama provider中实现stream_chat**（src/llm/ollama.py）
   - 使用httpx的stream方法
   - 逐行解析JSON并返回内容

4. **在handler中添加stream_handle_message方法**（src/companion/handler.py）
   - 流式处理用户消息
   - 逐token返回
   - 最后保存完整回复并提取信息

5. **在API中添加SSE流式端点**（src/api/chat.py）
   - 新增 POST /api/chat/stream 端点
   - 使用Server-Sent Events (SSE) 返回流式数据
   - 事件类型：session（会话ID）、chunk（内容片段）、done（完成）

6. **修改前端JavaScript使用SSE**（src/api/chat.py）
   - 使用fetch + ReadableStream接收SSE
   - 实时更新UI显示
   - 添加formatMessage函数处理换行

**修改的文件**：
- `src/llm/base.py` - 添加stream_chat抽象方法
- `src/llm/openai_provider.py` - 实现stream_chat
- `src/llm/ollama.py` - 实现stream_chat
- `src/companion/handler.py` - 添加stream_handle_message方法
- `src/api/chat.py` - 添加SSE端点，修改前端JavaScript

**验证结果**：
```
✅ 语法检查通过
✅ LLM provider支持流式输出
✅ handler支持流式处理
✅ API添加SSE端点
✅ 前端实时显示输出
```

**技术细节**：

1. **SSE事件格式**：
   ```
   data: {"type": "session", "session_id": "xxx"}
   
   data: {"type": "chunk", "content": "你"}
   
   data: {"type": "chunk", "content": "好"}
   
   data: {"type": "done"}
   ```

2. **前端处理**：
   ```javascript
   const reader = resp.body.getReader();
   const decoder = new TextDecoder();
   
   while (true) {
     const { done, value } = await reader.read();
     if (done) break;
     
     const chunk = decoder.decode(value);
     // 解析SSE事件并更新UI
   }
   ```

**教训**：
1. **流式输出提升用户体验** - 实时看到输出比等待完整响应体验更好
2. **SSE是简单有效的方案** - 比WebSocket更简单，适合单向流式输出
3. **前后端配合** - 需要同时修改后端API和前端JavaScript
4. **兼容性考虑** - 保留原有的非流式端点，兼容旧客户端
