"""Database outbox dispatcher; lost broker acknowledgements remain recoverable."""

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import and_, or_, select, update

from backend.cleanup.models import ResourceCleanup
from backend.cleanup.repository import utcnow
from backend.infrastructure.database.session import SyncSessionLocal
from backend.task.celery_app import DOCUMENT_QUEUE, celery_app

logger = logging.getLogger(__name__)
LEASE_SECONDS = 300
DISPATCH_INTERVAL = 30


def due_jobs(now):
    return or_(
        and_(ResourceCleanup.status == "PENDING", ResourceCleanup.next_attempt_at <= now,
             ResourceCleanup.dispatch_after <= now),
        and_(ResourceCleanup.status == "PROCESSING", ResourceCleanup.lease_expires_at <= now),
    )


def dispatch_due(limit=100):
    now = utcnow()
    reserved_until = now + timedelta(seconds=LEASE_SECONDS)
    with SyncSessionLocal() as session:
        ids = session.scalars(select(ResourceCleanup.id).where(due_jobs(now)).order_by(
            ResourceCleanup.next_attempt_at, ResourceCleanup.id
        ).limit(limit)).all()
    published = 0
    for job_id in ids:
        with SyncSessionLocal() as session:
            changed = session.execute(update(ResourceCleanup).where(
                ResourceCleanup.id == job_id, due_jobs(now)
            ).values(status="PENDING", lease_token=None, lease_expires_at=None,
                     dispatch_after=reserved_until, next_attempt_at=now, updated_at=now)).rowcount
            session.commit()
        if not changed:
            continue
        try:
            celery_app.send_task("mmrag.cleanup_resources", args=[job_id],
                                 queue=DOCUMENT_QUEUE, retry=False)
            published += 1
        except Exception as exc:
            # Do not overwrite an already accepted/running worker after a lost ACK.
            with SyncSessionLocal() as session:
                session.execute(update(ResourceCleanup).where(
                    ResourceCleanup.id == job_id, ResourceCleanup.status == "PENDING",
                    ResourceCleanup.dispatch_after == reserved_until,
                ).values(dispatch_after=now + timedelta(seconds=DISPATCH_INTERVAL),
                         error_msg="清理任务暂未能投递，系统会自动重试。"))
                session.commit()
            logger.warning("cleanup publish failed job=%s error_type=%s", job_id, type(exc).__name__)
    return published


async def dispatch_loop():
    while True:
        try:
            await asyncio.to_thread(dispatch_due)
        except Exception as exc:
            logger.warning("cleanup dispatcher unavailable error_type=%s", type(exc).__name__)
        await asyncio.sleep(DISPATCH_INTERVAL)
