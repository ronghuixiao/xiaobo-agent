"""任务完成检测模块 - 使用LLM检测对话中是否提到任务完成"""

import sqlite3
import os
import json
import asyncio
import threading
from datetime import datetime
from typing import Optional


def detect_task_completion_sync(
    message: str,
    llm,
    logger=None
) -> None:
    """同步版本的任务完成检测（在新线程中运行）"""
    
    def _run_async():
        """在新线程中运行异步检测"""
        async def _async_detect():
            try:
                from src.llm.base import ChatMessage
                
                db = os.path.expanduser("~/.xiaobo-agent/memory.db")
                conn = sqlite3.connect(db, timeout=10)
                today = datetime.now().strftime("%Y-%m-%d")
                
                # 获取今天的待办任务
                pending_tasks = conn.execute(
                    "SELECT id, title FROM tasks WHERE date = ? AND status = 'pending'",
                    (today,)
                ).fetchall()
                
                if not pending_tasks:
                    if logger:
                        logger.info("🔍 无待办任务，跳过检测")
                    conn.close()
                    return
                
                if logger:
                    logger.info(f"🔍 检测任务完成: {message[:50]}...")
                    logger.info(f"🔍 待办任务: {[t[1] for t in pending_tasks]}")
                
                # 构建任务列表
                task_list = "\n".join([f"- {task_id}: {task_title}" for task_id, task_title in pending_tasks])
                
                # 使用LLM判断任务完成
                prompt = f"""判断用户消息中是否表达了某个任务已完成。
今天的待办任务：
{task_list}
用户消息："{message}"
规则：
- 判断是否表达"完成了/做完了/搞定了/OK了/结束了/通过了/交了/过了"等任何完成含义
- 只匹配列表中的任务
- 返回JSON数组，格式为[{{"task_id": "xxx", "completed": true}}]，没有匹配返回[]
只返回JSON。"""
                
                # 调用LLM
                if logger:
                    logger.info("🔍 调用LLM检测...")
                response = await llm.chat([ChatMessage(role="user", content=prompt)])
                if logger:
                    logger.info(f"🔍 LLM响应: {response.content[:200]}")
                
                # 解析LLM返回的JSON
                try:
                    # 提取JSON部分
                    response_text = response.content
                    start_idx = response_text.find('[')
                    end_idx = response_text.rfind(']') + 1
                    if start_idx != -1 and end_idx != -1:
                        json_str = response_text[start_idx:end_idx]
                        completed_tasks = json.loads(json_str)
                        if logger:
                            logger.info(f"🔍 解析到完成任务: {completed_tasks}")
                        
                        # 更新任务状态
                        for task in completed_tasks:
                            if task.get("completed") and task.get("task_id"):
                                task_id = task["task_id"]
                                # 验证任务ID是否在pending列表中
                                if any(t[0] == task_id for t in pending_tasks):
                                    conn.execute("UPDATE tasks SET status = 'done' WHERE id = ?", (task_id,))
                                    if logger:
                                        logger.info(f"✅ 任务已完成(LLM检测): {task_id}")
                                else:
                                    if logger:
                                        logger.warning(f"⚠️ 任务ID不在待办列表中: {task_id}")
                    else:
                        if logger:
                            logger.info("🔍 LLM响应中未找到JSON数组")
                except (json.JSONDecodeError, KeyError, TypeError) as e:
                    if logger:
                        logger.warning(f"解析LLM任务完成检测结果失败: {e}")
                
                conn.commit()
                conn.close()
            except Exception as e:
                if logger:
                    logger.warning(f"检测任务完成失败: {e}", exc_info=True)
        
        # 运行异步检测
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_async_detect())
        finally:
            loop.close()
    
    # 在新线程中运行
    thread = threading.Thread(target=_run_async, daemon=True)
    thread.start()
