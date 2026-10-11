"""Owned cleanup status and explicit retries of exhausted jobs."""

import asyncio
import logging

from backend.cleanup.repository import CleanupRepository, utcnow
from backend.core.errors import ServiceError

logger = logging.getLogger(__name__)


def public_job(row, file_name):
    return {
        "cleanup_job_id": row.id, "file_name": file_name,
        "raw_status": row.target_results.get("raw", "PENDING"),
        "vector_status": row.target_results.get("vectors", "PENDING"),
        **{name: getattr(row, name) for name in (
            "file_id", "kind", "target_generation", "status", "retry_count", "error_msg",
            "created_at", "updated_at", "completed_at", "next_attempt_at",
        )},
    }


class CleanupService:
    def __init__(self, db):
        self.repo = CleanupRepository(db)

    async def page(self, owner_id, **options):
        rows, cursor = await self.repo.page(owner_id, **options)
        return {"items": [public_job(row, name) for row, name in rows], "next_cursor": cursor}

    async def retry(self, job_id, owner_id):
        row, name = await self.repo.owned(job_id, owner_id, lock=True)
        if row.status == "SUCCESS":
            return public_job(row, name)
        if row.status != "FAILED":
            raise ServiceError("清理任务已在排队或处理中。", 409)
        row.status, row.retry_count, row.error_msg = "PENDING", 0, None
        row.next_attempt_at = row.dispatch_after = utcnow()
        row.lease_token = row.lease_expires_at = row.completed_at = None
        await self.repo.commit()
        from backend.cleanup.dispatch import dispatch_due
        try:
            await asyncio.to_thread(dispatch_due)
        except Exception as exc:
            logger.warning("cleanup retry dispatch unavailable job=%s error_type=%s", job_id, type(exc).__name__)
        return public_job(row, name)
