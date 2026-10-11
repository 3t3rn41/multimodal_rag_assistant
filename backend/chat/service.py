"""Ownership, feedback, history and preparation of existing RAG turns."""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from backend.chat.configuration import ChatConfiguration
from backend.chat.errors import ChatServiceError
from backend.chat.export import export_markdown
from backend.chat.models import (
    Message,
    MessageRole,
    Session,
    SessionMode,
    SessionStatus,
    Trace,
)
from backend.chat.repository import ChatRepository
from backend.chat.runtime import ACTIVE_TURNS
from backend.chat.types import StreamState
from backend.core.errors import ServiceError
from backend.infrastructure.database.session import SessionLocal
from backend.infrastructure.jina.configuration import jina_profile
from backend.model_settings.service import ModelSettingsService
from rag_engine.models import Chunk


@dataclass
class PreparedTurn:
    session_id: int
    chunks: list[Chunk]
    config: ChatConfiguration
    question: str
    history: list[dict[str, str]]


class ChatService:
    def __init__(self, db):
        self.repo = ChatRepository(db)
        self.models = ModelSettingsService()

    @staticmethod
    async def recover_interrupted(*, session_factory=SessionLocal):
        async with session_factory() as db:
            repo = ChatRepository(db)
            count = await repo.recover_executing()
            await repo.commit()
            return count

    async def chat_configuration(self):
        llm = await self.models.answer_configuration()
        return ChatConfiguration.from_answer(llm)

    async def owned(self, session_id, owner_id):
        conversation = await self.repo.get(session_id)
        if conversation is None or conversation.user_id != owner_id:
            raise ServiceError("会话不存在", 404)
        return conversation

    @staticmethod
    def view(conversation, kb_ids):
        return {
            "id": conversation.id,
            "mode": conversation.mode,
            "status": conversation.status,
            "title": conversation.title,
            "token_used": conversation.token_used,
            "cost": conversation.cost,
            "created_time": conversation.created_time,
            "kb_ids": kb_ids,
        }

    async def list(self, owner_id):
        rows = await self.repo.sessions(owner_id)
        scopes = {}
        if rows:
            for sid, kid in await self.repo.scopes([row.id for row in rows]):
                scopes.setdefault(sid, []).append(kid)
        return [self.view(row, scopes.get(row.id, [])) for row in rows]

    async def detail(self, session_id, owner_id):
        row = await self.owned(session_id, owner_id)
        return self.view(row, [kid for _, kid in await self.repo.scopes([session_id])])

    async def messages(self, session_id, owner_id):
        await self.owned(session_id, owner_id)
        return await self.repo.messages(session_id)

    async def delete(self, session_id, owner_id):
        row = await self.owned(session_id, owner_id)
        if session_id in ACTIVE_TURNS or row.status == SessionStatus.EXECUTING:
            raise ServiceError("会话正在运行中，无法删除", 409)
        await self.repo.remove_conversation(row)
        await self.repo.commit()

    async def rename(self, session_id, owner_id, title):
        row = await self.owned(session_id, owner_id)
        row.title = title.strip()
        await self.repo.commit()
        await self.repo.refresh(row)
        return await self.detail(session_id, owner_id)

    async def feedback(self, session_id, message_id, owner_id, feedback):
        await self.owned(session_id, owner_id)
        message = await self.repo.message(message_id)
        if message is None or message.session_id != session_id:
            raise ServiceError("消息不存在", 404)
        old = message.feedback
        message.feedback = feedback
        if old != feedback:
            kb_ids = [kid for _, kid in await self.repo.scopes([session_id])]
            file_ids = {
                c.get("doc_id")
                for c in (message.refs or [])
                if isinstance(c, dict) and c.get("doc_id")
            }
            if kb_ids and file_ids:
                for link in await self.repo.feedback_memberships(kb_ids, file_ids):
                    if old in {"up", "down"}:
                        field = f"feedback_{old}"
                        setattr(link, field, max(0, (getattr(link, field) or 0) - 1))
                    if feedback in {"up", "down"}:
                        field = f"feedback_{feedback}"
                        setattr(link, field, (getattr(link, field) or 0) + 1)
        await self.repo.commit()
        await self.repo.refresh(message)
        return message

    async def trace(self, session_id, owner_id):
        row = await self.owned(session_id, owner_id)
        turns = [
            {
                "message_id": t.message_id,
                "created_at": t.created_at,
                "metrics": t.metrics or {},
                "steps": t.steps or [],
            }
            for t in await self.repo.traces(session_id)
        ]
        return {"session_id": session_id, "mode": row.mode.value, "turns": turns}

    async def usage(self, session_id, owner_id):
        row = await self.owned(session_id, owner_id)
        turns = [
            {
                "message_id": t.message_id,
                "created_at": t.created_at,
                "metrics": t.metrics or {},
            }
            for t in await self.repo.traces(session_id)
        ]
        return {
            "session_id": session_id,
            "mode": row.mode.value,
            "created_time": row.created_time,
            "total_tokens": row.token_used or 0,
            "cost": row.cost or 0.0,
            "message_count": await self.repo.message_count(session_id),
            "turn_count": len(turns),
            "turns": turns,
        }

    async def export(self, session_id, owner_id):
        row = await self.owned(session_id, owner_id)
        return export_markdown(row, await self.repo.messages(session_id))

    async def prepare_turn(self, owner_id, question, kb_ids, session_id):
        question = question.strip()
        if not question:
            raise ServiceError("请输入问题。")
        try:
            kb_ids = _single_scope(kb_ids)
            if session_id is not None:
                await _continuing_session(self.repo, owner_id, session_id, kb_ids[0])
            kb_ids, chunks = await load_scoped_chunks(self.repo.db, owner_id, kb_ids)
            config = await self.chat_configuration()
            profile = jina_profile()
            if any(
                c.extra.get("vector_collection") != config.collection
                or c.extra.get("embedding_space") != profile["embedding_space"]
                for c in chunks
            ):
                raise ServiceError(
                    "所选知识库含旧向量模型的文档。请在知识库重新解析这些文档，完成后再提问。",
                    409,
                )
            sid, history = await begin_turn(
                self.repo.db, owner_id, kb_ids, question, session_id, chunks
            )
        except ChatServiceError as exc:
            raise ServiceError(str(exc), exc.status_code) from None
        return PreparedTurn(sid, chunks, config, question, history)

    async def abort(self, session_id, owner_id):
        await self.owned(session_id, owner_id)
        flag = ACTIVE_TURNS.get(session_id)
        if flag is None:
            raise ServiceError("该会话未在运行中。", 409)
        flag.set()
        return {"aborted": True, "session_id": session_id}


def _single_scope(kb_ids: Sequence[int]) -> list[int]:
    if len(kb_ids) != 1:
        raise ChatServiceError("请选择一个知识库后再提问。", 400)
    return list(kb_ids)


async def _continuing_session(repo, owner_id, session_id, kb_id):
    session = await repo.get(session_id)
    if session is None or session.user_id != owner_id:
        raise ChatServiceError("会话不存在。", 404)
    if session.mode != SessionMode.CHAT:
        raise ChatServiceError("该会话不是问答会话。", 400)
    scopes = await repo.scopes([session_id])
    if len(scopes) != 1 or scopes[0][1] != kb_id:
        raise ChatServiceError("会话的知识库绑定不能更改，请新建会话。", 409)
    return session


async def load_scoped_chunks(
    db: AsyncSession,
    owner_id: int,
    kb_ids: Sequence[int],
) -> tuple[list[int], list[Chunk]]:
    """Load only owned, enabled, ready documents' current canonical chunks."""
    scope = _single_scope(kb_ids)
    repo = ChatRepository(db)
    owned = await repo.owned_knowledge_ids(owner_id, scope)
    if owned != set(scope):
        raise ChatServiceError("所选知识库不存在或不属于当前用户。", 404)
    rows = await repo.scoped_chunks(owner_id, scope)
    chunks = [Chunk.from_payload(row.payload, fallback_id=row.chunk_id) for row in rows]
    if not chunks:
        raise ChatServiceError(
            "所选知识库尚无可检索的文档切片。请先上传 PDF、DOCX、TXT 或 MD，等待解析与向量化完成；"
            "失败的文件可在知识库页面查看原因并重试。",
            409,
        )
    return scope, chunks


async def begin_turn(
    db: AsyncSession,
    owner_id: int,
    kb_ids: Sequence[int],
    question: str,
    session_id: int | None,
    chunks: Sequence[Chunk],
) -> tuple[int, list[dict[str, str]]]:
    repo = ChatRepository(db)
    kb_ids = _single_scope(kb_ids)
    if session_id is None:
        session = Session(
            user_id=owner_id,
            mode=SessionMode.CHAT,
            status=SessionStatus.EXECUTING,
            title=question[:100],
        )
        await repo.create(session)
        repo.bind_knowledge(session.id, kb_ids[0])
    else:
        session = await _continuing_session(repo, owner_id, session_id, kb_ids[0])
        if not await repo.acquire_turn(session.id):
            raise ChatServiceError("该会话正在生成回答，请等待完成或中断。", 409)
    session_id = session.id
    history_rows = await repo.history(session_id)
    allowed = {chunk.chunk_id for chunk in chunks}
    history = []
    budget = 12_000
    for message in history_rows:  # Most recent messages get the budget first.
        if message.role == MessageRole.ASSISTANT and any(
            str(c.get("chunk_id")) not in allowed
            for c in (message.refs or [])
            if isinstance(c, dict)
        ):
            continue
        content = message.content or ""
        if len(content) > budget:
            break
        budget -= len(content)
        history.append({"role": message.role.value, "content": content})
    history.reverse()
    repo.add(Message(session_id=session_id, role=MessageRole.USER, content=question))
    await repo.commit()  # Persist before StreamingResponse returns.
    return session_id, history


async def persist_turn(
    session_id: int, state: StreamState, *, session_factory=SessionLocal
) -> int:
    """Independent DB transaction survives request closure and cancellation."""
    async with session_factory() as db:
        repo = ChatRepository(db)
        message = Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            content=state.answer,
            refs=state.citations or None,
        )
        await repo.create(message)
        duration = int((time.monotonic() - state.started) * 1000)
        repo.add(
            Trace(
                session_id=session_id,
                message_id=message.id,
                steps=[
                    {**step, "status": state.status.value}
                    if step.get("status") == "running"
                    else step
                    for step in state.steps
                ],
                metrics={
                    "pipeline": "member-b-c-rag",
                    "finish_reason": state.status.value,
                    "duration_ms": duration,
                    "retrieved_count": len(state.retrieved),
                    "citation_count": len(state.citations),
                    "error": state.error,
                    **state.model_profile,
                },
            )
        )
        session = await repo.get(session_id)
        if session is not None:
            session.status = state.status
        await repo.commit()
        return message.id
