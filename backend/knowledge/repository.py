"""Knowledge-base membership data access."""

from sqlalchemy import delete, select

from backend.chat.models import SessionScope
from backend.infrastructure.database.repository import AsyncRepository
from backend.knowledge.models import KBDocument, KnowledgeBase
from backend.upload.models import Document


class KnowledgeRepository(AsyncRepository):
    async def get(self, kb_id, *, lock=False):
        if lock:
            return (await self.db.execute(
                select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
                .with_for_update().execution_options(populate_existing=True)
            )).scalar_one_or_none()
        return await self.db.get(KnowledgeBase, kb_id)

    async def list(self, owner_id):
        return list(
            (
                await self.db.scalars(
                    select(KnowledgeBase)
                    .where(KnowledgeBase.owner_id == owner_id)
                    .order_by(KnowledgeBase.created_at.desc())
                )
            ).all()
        )

    async def membership(self, kb_id, file_id, *, lock=False):
        statement = select(KBDocument).where(
            KBDocument.kb_id == kb_id, KBDocument.file_id == file_id
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (
            await self.db.execute(statement)
        ).scalar_one_or_none()

    async def file_ids(self, kb_id):
        return list((await self.db.scalars(
            select(KBDocument.file_id).where(KBDocument.kb_id == kb_id)
            .order_by(KBDocument.file_id).with_for_update()
        )).all())

    async def has_memberships(self, file_id):
        # Locking reads see committed links even under MySQL REPEATABLE READ.
        return (await self.db.execute(
            select(KBDocument.id).where(KBDocument.file_id == file_id)
            .limit(1).with_for_update()
        )).first() is not None

    async def files(self, kb_id):
        return (
            await self.db.execute(
                select(KBDocument, Document)
                .join(Document, KBDocument.file_id == Document.id)
                .where(KBDocument.kb_id == kb_id, Document.deleted_at.is_(None))
                .order_by(KBDocument.created_at.desc())
            )
        ).all()

    async def remove_knowledge(self, kb):
        await self.db.execute(delete(KBDocument).where(KBDocument.kb_id == kb.id))
        await self.db.execute(delete(SessionScope).where(SessionScope.kb_id == kb.id))
        await self.db.delete(kb)
