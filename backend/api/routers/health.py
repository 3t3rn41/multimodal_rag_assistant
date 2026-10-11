"""健康检查路由。

两个端点的区别（对应 K8s 探针语义）：
- /health（liveness）：进程活着就返回 ok，不碰任何依赖。用于"该不该重启容器"。
- /ready（readiness）：实际探活 MySQL 与 Redis。用于"该不该把流量打进来"。
  任一依赖不通则 503，负载均衡据此摘除实例。
"""

from __future__ import annotations

import os

import httpx
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from backend.core.config import settings
from backend.infrastructure.database.session import engine
from backend.infrastructure.redis import async_client

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    """存活探针：无依赖检查。"""
    return {"status": "ok"}


@router.get("/ready")
async def ready():
    """就绪探针：检查 MySQL、Redis、MinIO 与 Qdrant 连通性，任一不通返回 503。"""
    checks: dict[str, str] = {}

    # MySQL
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["mysql"] = "ok"
    except Exception as exc:  # noqa: BLE001 — 探针需捕获一切并降级
        checks["mysql"] = f"error: {exc.__class__.__name__}"

    # Redis
    redis = async_client(settings.redis_url, socket_timeout=2)
    try:
        await redis.ping()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"error: {exc.__class__.__name__}"
    finally:
        await redis.aclose()

    # Probe only local infrastructure; never invoke model APIs from readiness.
    try:
        async with httpx.AsyncClient(timeout=2.0, trust_env=False) as client:
            scheme = "https" if settings.env.minio_secure else "http"
            response = await client.get(
                f"{scheme}://{settings.env.minio_endpoint}/minio/health/live"
            )
            response.raise_for_status()
        checks["minio"] = "ok"
    except Exception as exc:  # noqa: BLE001 - report safe local infrastructure status
        checks["minio"] = f"error: {exc.__class__.__name__}"

    try:
        url = (
            os.getenv("RAG_QDRANT_URL")
            or f"http://{settings.env.qdrant_host}:{settings.env.qdrant_port}"
        )
        headers = (
            {"api-key": os.environ["RAG_QDRANT_API_KEY"]}
            if os.getenv("RAG_QDRANT_API_KEY")
            else {}
        )
        async with httpx.AsyncClient(timeout=2.0, trust_env=False) as client:
            response = await client.get(url.rstrip("/") + "/readyz", headers=headers)
            response.raise_for_status()
        checks["qdrant"] = "ok"
    except Exception as exc:  # noqa: BLE001 - safe probe without secrets
        checks["qdrant"] = f"error: {exc.__class__.__name__}"

    from backend.infrastructure.jina.configuration import configuration_status

    models = configuration_status()
    # No paid provider calls from readiness. Missing mandatory configuration is
    # exposed explicitly and blocks production readiness; development can still
    # start for configuration, registration and diagnostic work.
    healthy = all(value == "ok" for value in checks.values())
    checks["embedding"] = (
        "configured_not_verified"
        if models["embedding_configured"]
        else "missing_configuration"
    )
    checks["rerank"] = (
        "configured_not_verified"
        if models["rerank_configured"]
        else "missing_configuration"
    )
    if settings.env.app_env == "production":
        healthy = healthy and models["configured"]
    return JSONResponse(
        status_code=status.HTTP_200_OK
        if healthy
        else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "status": "ready" if healthy else "degraded",
            "checks": checks,
            "system_models": models,
        },
    )
