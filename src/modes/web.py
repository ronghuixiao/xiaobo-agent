"""Web API 模式 - 仅启动 API 服务"""

from src.api.phone import create_phone_router
from src.api.routes import create_api_router
from src.llm.factory import create_llm_provider
from src.memory.database import MemoryDatabase
from src.companion.task_manager import TaskManager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn


async def web_mode(settings):
    """Web API 模式 - 仅启动 API 服务"""
    llm = create_llm_provider(settings.llm)
    memory = MemoryDatabase(settings.memory.db_path)
    await memory.initialize()
    task_mgr = TaskManager(settings.memory.db_path)

    app = FastAPI(title="小柏 Agent API", version="0.3.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(create_phone_router())
    app.include_router(create_api_router(memory=memory, task_mgr=task_mgr))

    print(f"🌐 小柏 API 服务启动: http://0.0.0.0:8088")
    config = uvicorn.Config(app, host="0.0.0.0", port=8088)
    server = uvicorn.Server(config)
    await server.serve()
