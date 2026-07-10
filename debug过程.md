
---

### 问题22：LLM幻觉 - 相对时间词导致时间错位

**现象**：
用户和小柏agent对话时，小柏说"对了，你昨晚梦到去了四川"，但这个事实实际上是前天晚上的，不是昨晚的。

**根因分析**：

1. **ExtractedFact没有事件发生时间字段** - 只有 `created_at`（提取时间），没有 `event_time`（事件发生时间）

2. **提取prompt没有要求提取时间信息** - EXTRACTION_PROMPT只要求提取事实内容，没有要求提取时间

3. **数据库中的记录**：
   ```
   content: "用户昨晚梦到自己去了四川..."
   created_at: 2026-07-08T15:27:09  (7月8日下午3点提取)
   ```
   - 7月8日提取时，"昨晚"指的是7月7日晚上
   - 现在是7月10日，小柏agent看到"昨晚梦到四川"，会认为是7月9日晚上
   - **相对时间词在存储后会失去时间锚点，导致时间错位**

4. **LLM在生成回复时可能添加时间修饰词** - 当LLM看到"梦到四川"这个事实时，可能会自己添加"昨晚"、"前天"等时间词

**修复方案**：

1. **在ExtractedFact中添加event_time字段**（src/memory/base.py）
   ```python
   event_time: Optional[str] = None  # 事件发生时间（绝对时间，如"2026-07-07晚上"）
   ```

2. **修改提取prompt要求使用绝对时间**（src/companion/extractor.py）
   - 添加当前时间到prompt
   - 要求LLM使用绝对时间，不要使用"昨晚"、"前天"等相对时间词
   - 提供转换示例

3. **修改_get_known_facts格式化包含时间**（src/companion/handler.py）
   - 格式化时包含event_time字段
   - 例如：`- [event] 用户梦境事件: 用户梦到自己去了四川 [2026-07-07晚上]`

4. **在system prompt中添加约束**（src/companion/handler.py）
   - 告诉LLM不要猜测时间
   - 如果记忆中没有event_time，不要添加时间描述

5. **数据库schema更新**（src/memory/database.py）
   - facts表添加event_time字段
   - save_fact和get_facts函数添加event_time处理

**修改的文件**：
- `src/memory/base.py` - ExtractedFact添加event_time字段
- `src/memory/database.py` - facts表添加event_time字段，save_fact和get_facts函数更新
- `src/companion/extractor.py` - 提取prompt添加时间要求
- `src/companion/handler.py` - _get_known_facts格式化包含时间，system prompt添加约束

**验证结果**：
```
✅ 语法检查通过
✅ 数据库已添加event_time字段
✅ 提取prompt要求使用绝对时间
✅ 格式化包含时间信息
✅ system prompt约束LLM不要猜测时间
```

**教训**：
1. **相对时间词不能直接存储** - "昨晚"、"前天"等词在存储后会失去时间锚点
2. **必须使用绝对时间** - 存储时应该转换为"2026-07-07晚上"这样的绝对时间
3. **LLM需要明确约束** - 不约束的话，LLM可能会自己添加时间修饰词
4. **时间信息要完整** - 不仅要存储事实内容，还要存储事件发生时间
