from backend.knowledge.models import KnowledgeBase
from backend.upload.models import Document, ParseStatus, RagChunk

"""Conversation history and streaming transactions' data access."""

from sqlalchemy import delete, func, select, update

from backend.chat.models import (
    Message,
    MessageRole,
    Session,
    SessionScope,
    SessionStatus,
    Trace,
)
from backend.infrastructure.database.repository import AsyncRepository
from backend.knowledge.models import KBDocument


class ChatRepository(AsyncRepository):
    async def get(self, session_id):
        return await self.db.get(Session, session_id)

    async def sessions(self, owner_id):
        return list(
            (
                await self.db.scalars(
                    select(Session)
                    .where(Session.user_id == owner_id)
                    .order_by(Session.created_time.desc())
                )
            ).all()
        )

    async def scopes(self, session_ids):
        return (
            await self.db.execute(
                select(SessionScope.session_id, SessionScope.kb_id).where(
                    SessionScope.session_id.in_(session_ids)
                )
            )
        ).all()

    async def messages(self, session_id):
        return list(
            (
                await self.db.scalars(
                    select(Message)
                    .where(Message.session_id == session_id)
                    .order_by(Message.id)
                )
            ).all()
        )

    async def history(self, session_id):
        return list(
            (
                await self.db.scalars(
                    select(Message)
                    .where(
                        Message.session_id == session_id,
                        Message.role.in_([MessageRole.USER, MessageRole.ASSISTANT]),
                    )
                    .order_by(Message.id.desc())
                    .limit(12)
                )
            ).all()
        )

    async def message(self, message_id):
        return await self.db.get(Message, message_id)

    async def traces(self, session_id):
        return list(
            (
                await self.db.scalars(
                    select(Trace)
                    .where(Trace.session_id == session_id)
                    .order_by(Trace.id)
                )
            ).all()
        )

    async def message_count(self, session_id):
        return (
            await self.db.execute(
                select(func.count())
                .select_from(Message)
                .where(Message.session_id == session_id)
            )
        ).scalar_one()

    async def feedback_memberships(self, kb_ids, file_ids):
        return list(
            (
                await self.db.scalars(
                    select(KBDocument).where(
                        KBDocument.kb_id.in_(kb_ids), KBDocument.file_id.in_(file_ids)
                    )
                )
            ).all()
        )

    async def acquire_turn(self, session_id):
        result = await self.db.execute(
            update(Session)
            .where(Session.id == session_id, Session.status != SessionStatus.EXECUTING)
            .values(status=SessionStatus.EXECUTING)
        )
        return result.rowcount == 1

    def bind_knowledge(self, session_id, kb_id):
        self.db.add(SessionScope(session_id=session_id, kb_id=kb_id))

    async def remove_conversation(self, conversation):
        for model in (Trace, Message, SessionScope):
            await self.db.execute(
                delete(model).where(model.session_id == conversation.id)
            )
        await self.db.delete(conversation)

    async def recover_executing(self):
        result = await self.db.execute(
            update(Session)
            .where(Session.status == SessionStatus.EXECUTING)
            .values(status=SessionStatus.ERROR)
        )
        return result.rowcount

    async def owned_knowledge_ids(self, owner_id: int, kb_ids):
        return set(
            (
                await self.db.scalars(
                    select(KnowledgeBase.id).where(
                        KnowledgeBase.id.in_(kb_ids), KnowledgeBase.owner_id == owner_id
                    )
                )
            ).all()
        )

    async def scoped_chunks(self, owner_id: int, kb_ids):
        return list(
            (
                await self.db.scalars(
                    select(RagChunk)
                    .join(Document, Document.id == RagChunk.file_id)
                    .join(KBDocument, KBDocument.file_id == Document.id)
                    .where(
                        KBDocument.kb_id.in_(kb_ids),
                        KBDocument.enabled.is_(True),
                        Document.owner_id == owner_id,
                        Document.deleted_at.is_(None),
                        Document.status == ParseStatus.DONE,
                        RagChunk.generation == Document.version,
                    )
                    .order_by(RagChunk.chunk_id)
                )
            )
            .unique()
            .all()
        )
