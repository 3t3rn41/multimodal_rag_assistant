"""Installed capabilities and configuration presence; never probes paid models."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import get_current_user
from backend.auth.models import User
from backend.core.config import settings
from backend.infrastructure.database.session import get_session
from backend.infrastructure.jina.configuration import configuration_status
from backend.model_settings.service import ModelSettingsService

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/status")
async def system_status(
    current: Annotated[User, Depends(get_current_user)],
):
    configuration = configuration_status()
    cfg = await ModelSettingsService().get()
    configuration = {
        **configuration,
        "llm_configured": cfg["llm_key_configured"] and bool(cfg["llm_model"]),
        "configured": cfg["configured"] and configuration["configured"],
        "missing": [*cfg["missing"], *configuration["missing"]],
    }
    return {
        "application": "multimodal_rag_assistant",
        "stage": settings.env.app_stage,
        "storage": "mysql+minio",
        "team_ingestion_connected": True,
        "team_rag_connected": True,
        "configuration": configuration,
        "capabilities": {
            "knowledge_management": True,
            "file_storage": True,
            "chunked_upload": False,
            "celery_tasks": True,
            "pdf_rag": True,
            "sse_chat": True,
            "session_persistence": True,
            "document_citations": True,
            "email_login": True,
            "online_model_settings": False,
            "multimodal_playback": False,
        },
    }


@router.get("/worker")
async def worker_status(
    request: Request, db: Annotated[AsyncSession, Depends(get_session)]
):
    if settings.env.app_env == "production":
        await get_current_user(request, db)
    from backend.task.celery_app import QUEUE_PREFIX, celery_app

    def ping():
        result = celery_app.control.inspect(timeout=2).ping() or {}
        return any(name.startswith(f"{QUEUE_PREFIX}@") for name in result)

    try:
        online = await asyncio.to_thread(ping)
    except Exception:  # noqa: BLE001 - diagnostic must not expose broker errors
        online = False
    return {"online": online, "queue": f"{QUEUE_PREFIX}.documents"}
