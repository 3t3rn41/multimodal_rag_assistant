"""Async task API reads and synchronous worker persistence."""

from sqlalchemy import select

from backend.infrastructure.database.repository import AsyncRepository
from backend.task.models import IngestionTask
from backend.upload.models import Document, RagChunk


class TaskRepository(AsyncRepository):
    async def file(self, file_id: int, *, lock=False):
        if lock:
            return (
                await self.db.execute(
                    select(Document)
                    .where(Document.id == file_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).scalar_one_or_none()
        return await self.db.get(Document, file_id)

    async def get(self, task_id: str):
        return await self.db.get(IngestionTask, task_id)

    async def active(self, file_id: int, generation: int | None = None, *, lock=False):
        statement = select(IngestionTask).where(
            IngestionTask.file_id == file_id,
            IngestionTask.status.in_(["PENDING", "PROCESSING"]),
        )
        if generation is not None:
            statement = statement.where(IngestionTask.generation == generation)
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return list((await self.db.scalars(statement)).all())


class WorkerRepository:
    """The worker shares one transaction for task, file and chunk state."""

    def __init__(self, db):
        self.db = db

    def current(self, task_id: str):
        task = self.db.get(IngestionTask, task_id)
        if task is None:
            return None, None
        doc = self.db.execute(
            select(Document).where(Document.id == task.file_id).with_for_update()
        ).scalar_one_or_none()
        return task, doc

    def chunks(self, file_id: int, generation: int):
        return self.db.scalars(
            select(RagChunk)
            .where(RagChunk.file_id == file_id, RagChunk.generation == generation)
            .order_by(RagChunk.chunk_id)
        ).all()

    def add(self, row):
        self.db.add(row)

    def commit(self):
        self.db.commit()
