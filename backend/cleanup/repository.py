"""Shared job construction and owned cleanup API queries."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import and_, or_, select

from backend.cleanup.models import ResourceCleanup
from backend.core.errors import ServiceError
from backend.infrastructure.database.repository import AsyncRepository
from backend.infrastructure.storage import BUCKET
from backend.upload.models import Document, RagChunk


def utcnow():
    # MySQL DATETIME columns use seconds; reservation comparisons must match.
    return datetime.now(UTC).replace(tzinfo=None, microsecond=0)


def new_job(doc, kind="deleted_file", generation=0):
    now = utcnow()
    original = kind == "deleted_file"
    bucket = ((doc.meta or {}).get("storage_bucket") or BUCKET) if original else None
    return ResourceCleanup(
        id=str(uuid4()), owner_id=doc.owner_id, file_id=doc.id,
        kind=kind, target_generation=generation,
        object_bucket=bucket,
        object_key=doc.storage_path if original else None,
        target_results={"raw": "PENDING" if original else "SKIPPED", "vectors": "PENDING", "collections": []},
        status="PENDING", retry_count=0, next_attempt_at=now, dispatch_after=now,
    )


def schedule_superseded(session, doc):
    """Called under the file row lock, in the successful indexing transaction."""
    generations = session.scalars(
        select(RagChunk.generation).where(RagChunk.file_id == doc.id, RagChunk.generation < doc.version).distinct()
    ).all()
    scheduled = set(session.scalars(
        select(ResourceCleanup.target_generation).where(
            ResourceCleanup.file_id == doc.id, ResourceCleanup.kind == "superseded_generation"
        )
    ).all())
    for generation in generations:
        if generation not in scheduled:
            session.add(new_job(doc, "superseded_generation", generation))


class CleanupRepository(AsyncRepository):
    async def for_deleted_file(self, doc):
        row = (await self.db.execute(select(ResourceCleanup).where(
            ResourceCleanup.file_id == doc.id, ResourceCleanup.kind == "deleted_file",
            ResourceCleanup.target_generation == 0,
        ).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
        if row is None:
            row = new_job(doc)
            await self.create(row)
        return row

    async def owned(self, job_id, owner_id, *, lock=False):
        statement = select(ResourceCleanup, Document.file_name).join(Document, Document.id == ResourceCleanup.file_id).where(
            ResourceCleanup.id == job_id, ResourceCleanup.owner_id == owner_id
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        row = (await self.db.execute(statement)).one_or_none()
        if row is None:
            raise ServiceError("清理任务不存在。", 404)
        return row

    async def page(self, owner_id, status=None, cursor=None, limit=20):
        statement = select(ResourceCleanup, Document.file_name).join(Document, Document.id == ResourceCleanup.file_id).where(
            ResourceCleanup.owner_id == owner_id
        )
        if status:
            statement = statement.where(ResourceCleanup.status == status)
        if cursor:
            await self.owned(cursor, owner_id)
            # Compare native DB timestamps rather than re-serializing their precision.
            boundary_time = select(ResourceCleanup.created_at).where(ResourceCleanup.id == cursor).scalar_subquery()
            statement = statement.where(or_(
                ResourceCleanup.created_at < boundary_time,
                and_(ResourceCleanup.created_at == boundary_time, ResourceCleanup.id < cursor),
            ))
        rows = list((await self.db.execute(statement.order_by(
            ResourceCleanup.created_at.desc(), ResourceCleanup.id.desc()
        ).limit(limit + 1))).all())
        return rows[:limit], rows[limit - 1][0].id if len(rows) > limit else None
