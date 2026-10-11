"""Uploaded file, canonical chunk and document-scope database access."""

from sqlalchemy import delete, select

from backend.auth.models import User
from backend.infrastructure.database.repository import AsyncRepository
from backend.knowledge.models import KBDocument
from backend.upload.models import Document, RagChunk


class FileRepository(AsyncRepository):
    async def lock_owner(self, owner_id: int):
        # Serialize membership changes before locking files, including bulk deletion.
        await self.db.execute(select(User.id).where(User.id == owner_id).with_for_update())

    async def get(self, file_id: int, *, lock=False):
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

    async def chunk(self, chunk_id: str, *, lock=False):
        statement = select(RagChunk).where(RagChunk.chunk_id == chunk_id)
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (
            await self.db.execute(statement)
        ).scalar_one_or_none()

    async def chunks(self, file_id: int, generation: int):
        return list(
            (
                await self.db.scalars(
                    select(RagChunk)
                    .where(
                        RagChunk.file_id == file_id, RagChunk.generation == generation
                    )
                    .order_by(RagChunk.chunk_id)
                )
            ).all()
        )

    async def unlink(self, file_id: int):
        await self.db.execute(delete(KBDocument).where(KBDocument.file_id == file_id))
