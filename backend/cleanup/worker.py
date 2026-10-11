"""Fenced, idempotent cleanup using the same document lock as ingestion."""

import logging
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import delete, select

from backend.cleanup.dispatch import LEASE_SECONDS
from backend.cleanup.models import ResourceCleanup
from backend.cleanup.repository import utcnow
from backend.infrastructure.database.session import SyncSessionLocal
from backend.infrastructure.qdrant import delete_points
from backend.infrastructure.redis import distributed_lock
from backend.infrastructure.storage import delete_object, get_minio_client
from backend.task.celery_app import BROKER_URL, QUEUE_PREFIX, celery_app
from backend.task.retry import transient_error
from backend.upload.models import Document, RagChunk

logger = logging.getLogger(__name__)
MAX_RETRIES = 3


class LostCleanupLease(RuntimeError):
    pass


def _claim(job_id):
    now = utcnow()
    with SyncSessionLocal() as session:
        row = session.execute(select(ResourceCleanup).where(ResourceCleanup.id == job_id).with_for_update()).scalar_one_or_none()
        if row is None or row.status in {"SUCCESS", "FAILED"}:
            return None
        if row.status == "PROCESSING" and row.lease_expires_at and row.lease_expires_at > now:
            return None
        if row.status == "PENDING" and row.next_attempt_at > now:
            return None
        doc = session.get(Document, row.file_id)
        if (doc is None or doc.owner_id != row.owner_id
                or (row.kind == "deleted_file" and doc.deleted_at is None)
                or (row.kind == "superseded_generation" and not 0 < row.target_generation < doc.version)
                or row.kind not in {"deleted_file", "superseded_generation"}):
            row.status, row.error_msg = "FAILED", "清理目标状态不匹配，未执行资源删除。"
            row.completed_at = now
            session.commit()
            return None
        row.status, row.lease_token = "PROCESSING", str(uuid4())
        row.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
        row.updated_at = now
        session.commit()
        return row


def _checkpoint(job, *, results=None, status=None, error=None, delay=None, retry_count=None):
    with SyncSessionLocal() as session:
        row = session.execute(select(ResourceCleanup).where(ResourceCleanup.id == job.id).with_for_update()).scalar_one()
        if row.status != "PROCESSING" or row.lease_token != job.lease_token:
            raise LostCleanupLease()
        now = utcnow()
        row.updated_at = now
        row.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
        if results is not None:
            row.target_results = dict(results)
        if status is not None:
            row.status, row.error_msg = status, error
            row.lease_token = row.lease_expires_at = None
            if delay is not None:
                row.next_attempt_at = row.dispatch_after = now + timedelta(seconds=delay)
            if status in {"SUCCESS", "FAILED"}:
                row.completed_at = now
            if status == "SUCCESS":
                chunks = delete(RagChunk).where(RagChunk.file_id == row.file_id)
                if row.target_generation:
                    chunks = chunks.where(RagChunk.generation == row.target_generation)
                session.execute(chunks)
        if retry_count is not None:
            row.retry_count = retry_count
        session.commit()


def _heartbeat(job, lock):
    lock.reacquire()
    _checkpoint(job)


def _vector_targets(job):
    statement = select(RagChunk.payload).where(RagChunk.file_id == job.file_id)
    if job.target_generation:
        statement = statement.where(RagChunk.generation == job.target_generation)
    with SyncSessionLocal() as session:
        rows = session.scalars(statement).all()
    collections = {}
    for payload in rows:
        extra = payload.get("extra", {})
        point_id = extra.get("qdrant_point_id")
        if point_id:
            collections.setdefault(extra.get("vector_collection"), set()).add(point_id)
    return collections


def _fail(job, errors):
    retry = all(transient_error(exc) for exc in errors) and job.retry_count < MAX_RETRIES
    count = job.retry_count + (1 if retry else 0)
    _checkpoint(job, status="PENDING" if retry else "FAILED", retry_count=count,
                delay=10 * 2**job.retry_count if retry else None,
                error="资源清理尚未完成，请检查 MinIO、Qdrant 或 Redis 服务。"
                      + ("系统会自动重试。" if retry else "修复服务后可手动重试。"))
    logger.warning("cleanup incomplete job=%s error_types=%s retry=%s",
                   job.id, ",".join(type(exc).__name__ for exc in errors), retry)
    return "PENDING" if retry else "FAILED"


@celery_app.task(name="mmrag.cleanup_resources")
def cleanup_resources(job_id):
    job = _claim(job_id)
    if job is None:
        return {"cleanup_job_id": job_id, "status": "IGNORED"}
    lock = None
    try:
        lock = distributed_lock(BROKER_URL, f"{QUEUE_PREFIX}:ingest:document:{job.file_id}", timeout=LEASE_SECONDS)
        if not lock.acquire(blocking=False):
            _checkpoint(job, status="PENDING", delay=10, error=job.error_msg)
            return {"cleanup_job_id": job_id, "status": "PENDING", "reason": "document_locked"}
        results = dict(job.target_results)
        results["collections"] = list(results.get("collections", []))
        errors = []
        if results.get("raw") == "PENDING":
            _heartbeat(job, lock)
            try:
                if job.object_key:
                    delete_object(get_minio_client(timeout=30), job.object_key, bucket=job.object_bucket)
                results["raw"] = "SUCCESS"
                _checkpoint(job, results=results)
            except LostCleanupLease:
                raise
            except Exception as exc:
                errors.append(exc)
        if results.get("vectors") == "PENDING":
            _heartbeat(job, lock)
            try:
                collections = _vector_targets(job)
                for collection, ids in collections.items():
                    if collection in results["collections"]:
                        continue
                    _heartbeat(job, lock)
                    try:
                        points = sorted(ids)
                        for start in range(0, len(points), 500):
                            _heartbeat(job, lock)
                            delete_points(points[start:start + 500], collection)
                        results["collections"].append(collection)
                        _checkpoint(job, results=results)
                    except LostCleanupLease:
                        raise
                    except Exception as exc:
                        errors.append(exc)
                if all(collection in results["collections"] for collection in collections):
                    results["vectors"] = "SUCCESS"
                    _checkpoint(job, results=results)
            except LostCleanupLease:
                raise
            except Exception as exc:
                errors.append(exc)
        if errors:
            status = _fail(job, errors)
        else:
            _checkpoint(job, status="SUCCESS")
            status = "SUCCESS"
        return {"cleanup_job_id": job_id, "status": status}
    except LostCleanupLease:
        return {"cleanup_job_id": job_id, "status": "IGNORED", "reason": "lease_lost"}
    except Exception as exc:
        try:
            status = _fail(job, [exc])
        except LostCleanupLease:
            status = "IGNORED"
        return {"cleanup_job_id": job_id, "status": status}
    finally:
        if lock is not None:
            try:
                if lock.owned():
                    lock.release()
            except Exception:
                logger.warning("cleanup lock release failed job=%s", job_id)
