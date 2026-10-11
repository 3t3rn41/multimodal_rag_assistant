"""FastAPI 应用装配；启动入口为 backend.api.main:app。"""

from __future__ import annotations

import logging
import asyncio
from contextlib import suppress
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.errors import register_error_openapi, register_exception_handlers
from backend.api.middleware import register_logging_middleware
from backend.api.routers.health import router as health_router
from backend.api.routers.system import router as system_router
from backend.auth.middleware import register_auth_middleware
from backend.auth.router import router as auth_router
from backend.chat.events import SSE_MODELS
from backend.chat.router import router as chat_router
from backend.chat.service import ChatService
from backend.cleanup.dispatch import dispatch_loop
from backend.cleanup.router import router as cleanup_router
from backend.chat.stream_router import router as rag_chat_router
from backend.core.config import settings
from backend.infrastructure.database import register_models
from backend.knowledge.router import router as kb_router
from backend.model_settings.router import router as models_router
from backend.task.router import router as task_router
from backend.upload.router import router as documents_router

API_PREFIX = "/api"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """startup: recover stuck EXECUTING sessions"""
    count = await ChatService.recover_interrupted()
    if count:
        logging.getLogger(__name__).warning(
            "Recovered %d interrupted chat sessions", count
        )
    dispatcher = asyncio.create_task(dispatch_loop())
    try:
        yield
    finally:
        dispatcher.cancel()
        with suppress(asyncio.CancelledError):
            await dispatcher


def create_app() -> FastAPI:
    register_models()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    app = FastAPI(
        title=settings.env.app_title,
        lifespan=lifespan,
        description="多模态 RAG 智能问答助手：PDF、DOCX、TXT、MD 文档解析、向量检索、流式问答与引用。",
        version="0.3.0",
    )

    # CORS：本地前端 dev server（项目 Vite 端口 5174）需要跨域
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            value.strip()
            for value in settings.env.app_cors_origins.split(",")
            if value.strip()
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_logging_middleware(app)
    register_auth_middleware(app)
    register_exception_handlers(app)

    # 健康检查挂在根路径（供探针/负载均衡），业务路由统一在 /api 下
    app.include_router(health_router)
    app.include_router(auth_router, prefix=API_PREFIX)
    app.include_router(models_router, prefix=API_PREFIX)
    app.include_router(system_router, prefix=API_PREFIX)
    app.include_router(task_router, prefix=API_PREFIX)
    app.include_router(rag_chat_router, prefix=API_PREFIX)
    app.include_router(documents_router, prefix=API_PREFIX)
    app.include_router(cleanup_router, prefix=API_PREFIX)
    app.include_router(kb_router, prefix=API_PREFIX)
    app.include_router(chat_router, prefix=API_PREFIX)

    @app.get("/", tags=["meta"])
    async def root():
        return {
            "name": settings.env.app_title,
            "stage": settings.env.app_stage,
            "docs": "/docs",
        }

    register_error_openapi(app, sse_models=SSE_MODELS)
    return app


# uvicorn 入口：`uvicorn backend.api.main:app`
app = create_app()
