"""Owned task status and durable dispatch before Redis publishing."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from uuid import uuid4

from backend.core.errors import ServiceError
from backend.infrastructure.jina.configuration import embedding_snapshot
from backend.task.celery_app import DOCUMENT_QUEUE, celery_app
from backend.task.errors import TaskConflictError
from backend.task.models import IngestionTask
from backend.task.progress import task_view, file_task_metadata
from backend.task.repository import TaskRepository
from backend.upload.models import Document, ParseStatus

logger = logging.getLogger(__name__)


class TaskService:
    def __init__(self, db):
        self.repo = TaskRepository(db)

    async def task_status(self, task_id, owner_id):
        task = await self.repo.get(task_id)
        if task is None:
            raise ServiceError("任务不存在。", 404)
        doc = await self.repo.file(task.file_id)
        if doc is None or doc.owner_id != owner_id or doc.deleted_at is not None:
            raise ServiceError("文档不存在。", 404)
        return task_view(task)

    async def cancel_for_file(self, file_id, when):
        tasks = await self.repo.active(file_id, lock=True)
        for task in tasks:
            task.status, task.sub_status, task.error_msg = (
                "FAILED",
                "CANCELLED",
                "文档已删除，任务已取消。",
            )
            task.completed_at = when
        # The enclosing file deletion commits the file and task changes together.
        return [task.id for task in tasks]

    async def revoke(self, task_ids):
        for task_id in task_ids:
            try:
                await asyncio.to_thread(
                    celery_app.control.revoke, task_id, terminate=False
                )
            except Exception:  # noqa: BLE001 - SQL cancellation remains authoritative.
                logger.warning("task revoke unavailable task=%s", task_id)

    async def enqueue_document(
        self, file_id: int, *, reparse: bool = False
    ) -> Document:
        repo = self.repo
        locked = await repo.file(file_id, lock=True)
        if locked is None or locked.deleted_at is not None:
            raise TaskConflictError("文档已删除。")
        active = await repo.active(file_id, locked.version, lock=True)
        if active:
            raise TaskConflictError("文档已在排队或处理中，请等待完成。")
        if reparse:
            locked.version += 1
        snapshot = embedding_snapshot(locked.owner_id)
        task = IngestionTask(
            id=str(uuid4()),
            file_id=file_id,
            generation=locked.version,
            status="PENDING",
            sub_status="QUEUED",
            progress=0,
            retry_count=0,
            configuration_snapshot=snapshot,
            task_type="document",
            failed_stage=None, stage_metrics=None, indexing_report=None,
        )
        repo.add(task)
        locked.status = ParseStatus.PENDING
        locked.meta = {
            **(locked.meta or {}),
            "pipeline_state": "team_ingestion",
            **file_task_metadata(task),
            "chunk_count": 0,
            "indexed_count": 0,
            "requires_reindex": False,
            "embedding_space": snapshot["embedding_space"],
            "vector_collection": snapshot["vector_collection"],
        }
        await repo.commit()
        # A committed row remains visible even when publishing fails; no zombie pending upload.
        try:
            await asyncio.to_thread(
                celery_app.send_task,
                "mmrag.ingest_document",
                args=[task.id],
                task_id=task.id,
                queue=DOCUMENT_QUEUE,
                retry=False,
            )
        except Exception as exc:  # noqa: BLE001 - store safe failure for any broker error
            logger.warning(
                "ingestion dispatch failed task=%s error_type=%s",
                task.id,
                type(exc).__name__,
            )
            # The publish acknowledgement can be lost after acceptance. Lock and check before
            # failing the row so that an already running worker's progress is never overwritten.
            locked = await repo.file(file_id, lock=True)
            await repo.refresh(task)
            if task.status == "PENDING" and task.sub_status == "QUEUED":
                error = "任务未能投递到 Redis。请启动 Redis 和后台 worker 后点击重试。"
                task.status, task.sub_status, task.error_msg = (
                    "FAILED",
                    "DISPATCH_FAILED",
                    error,
                )
                task.completed_at = datetime.now(UTC).replace(tzinfo=None)
                task.failed_stage = "DISPATCH_FAILED"
                locked.status = ParseStatus.FAILED
                locked.meta = {
                    **(locked.meta or {}),
                    **file_task_metadata(task),
                }
                await repo.commit()
        await repo.refresh(locked)
        return locked
