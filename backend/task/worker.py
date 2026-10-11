"""Celery task entry point: lease, finite retries and cancellation safety."""

from __future__ import annotations

import logging

from backend.infrastructure.database.session import SyncSessionLocal
from backend.infrastructure.jina.embedding import ModelProviderError
from backend.infrastructure.redis import distributed_lock
from backend.task.errors import (
    EmptyDocumentError,
    IngestionConfigurationError,
    InvalidTextEncodingError,
    StaleIngestionTask,
)
from backend.task.processing import _current, _process_ingestion, _update
from backend.task.retry import transient_error as _transient

from .celery_app import BROKER_URL, QUEUE_PREFIX, celery_app
from .repository import WorkerRepository

logger = logging.getLogger(__name__)
MAX_TASK_RETRIES = 3


def _safe_error(exc: Exception, stage: str) -> str:
    if isinstance(
        exc, (IngestionConfigurationError, EmptyDocumentError, InvalidTextEncodingError, ModelProviderError)
    ):
        return str(exc)
    if _transient(exc):
        return "服务连接失败、请求超时或限流。系统会有限次数自动重试；请检查网络、MinIO、模型服务和 Qdrant 服务。"
    if stage == "EMBEDDING":
        return "向量化或向量库配置校验失败。请检查 .env 中 Jina 密钥权限与 1024 维配置，重启后端和 Worker 后重试处理。"
    if stage == "INDEXING":
        return "向量入库未通过一致性检查。请检查 Qdrant 服务和集合配置后重试。"
    return "文档处理失败。请确认文件未损坏、包含可读取文字且格式为 PDF、DOCX、TXT 或 MD。"


@celery_app.task(bind=True, name="mmrag.ingest_document", max_retries=MAX_TASK_RETRIES)
def ingest_document(self, task_id: str) -> dict:
    """Enqueue using the durable ID as both the argument and Celery task ID."""
    lease = None
    try:
        with SyncSessionLocal() as session:
            task, _ = _current(session, task_id)
            doc_id = task.file_id
        lease = distributed_lock(
            BROKER_URL, f"{QUEUE_PREFIX}:ingest:document:{doc_id}", timeout=3600
        )
        if not lease.acquire(blocking=False):
            # The same generation is already running, or the previous generation
            # is winding down. Requeue without touching the active owner's progress.
            raise self.retry(countdown=10, max_retries=MAX_TASK_RETRIES)
        return _process_ingestion(task_id, lease)
    except StaleIngestionTask:
        return {
            "task_id": task_id,
            "status": "IGNORED",
            "reason": "superseded_or_deleted",
        }
    except Exception as exc:
        from celery.exceptions import Retry

        if isinstance(exc, Retry):
            raise
        retry = _transient(exc) and self.request.retries < MAX_TASK_RETRIES
        try:
            with SyncSessionLocal() as session:
                task, _ = _current(session, task_id)
                stage, progress = task.sub_status, task.progress
                task.retry_count = self.request.retries + (1 if retry else 0)
                task.failed_stage = stage
                WorkerRepository(session).commit()
            safe = _safe_error(exc, stage)
            _update(
                task_id,
                stage="RETRYING" if retry else stage,
                progress=progress,
                status="PENDING" if retry else "FAILED",
                error=safe,
            )
        except StaleIngestionTask:
            return {
                "task_id": task_id,
                "status": "IGNORED",
                "reason": "superseded_or_deleted",
            }
        logger.warning(
            "ingestion failure task_id=%s stage=%s error_type=%s retry=%s",
            task_id,
            stage,
            type(exc).__name__,
            retry,
        )
        if retry:
            raise self.retry(
                exc=RuntimeError(safe), countdown=10 * 2**self.request.retries
            )
        return {"task_id": task_id, "status": "FAILED", "error": safe}
    finally:
        if lease is not None:
            try:
                if lease.owned():
                    lease.release()
            except Exception:  # noqa: BLE001 - lock cleanup must not mask task result
                logger.warning("ingestion lock release failed task_id=%s", task_id)
