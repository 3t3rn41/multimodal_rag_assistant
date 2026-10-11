"""SSE transport of prepared document RAG turns and explicit cancellation."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import get_current_user
from backend.auth.models import User
from backend.chat.runtime import ACTIVE_TURNS
from backend.chat.schemas import AbortOut, ChatRequest
from backend.chat.service import ChatService, persist_turn
from backend.chat.streaming import stream_turn
from backend.infrastructure.database.session import get_session

router = APIRouter(tags=["chat"])


@router.post(
    "/chat",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "SSE 事件流；data 是含 event 的 JSON。开始流之前的失败返回 HTTP JSON，开始流之后使用 error 事件。事件 Schema 见 x-sse-events。",
            "content": {
                "text/event-stream": {
                    "schema": {"type": "string"},
                    "example": 'event: start\ndata: {"event":"start","session_id":"sess_1"}\n\n',
                }
            },
        }
    },
)
async def rag_chat(
    body: ChatRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    turn = await ChatService(session).prepare_turn(
        current.id, body.question, body.kb_ids, body.session_id
    )
    abort = asyncio.Event()
    ACTIVE_TURNS[turn.session_id] = abort

    async def events():
        try:
            async for frame in stream_turn(
                turn.session_id,
                turn.chunks,
                turn.config,
                turn.question,
                turn.history,
                abort,
                persist=persist_turn,
            ):
                yield frame
        finally:
            ACTIVE_TURNS.pop(turn.session_id, None)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/chat/sessions/{session_id}/abort", response_model=AbortOut)
async def abort_rag_chat(
    session_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    return await ChatService(session).abort(session_id, current.id)
