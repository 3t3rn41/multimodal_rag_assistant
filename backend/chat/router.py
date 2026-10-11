"""Conversation HTTP contracts backed by Member A's ChatService."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.responses import MarkdownResponse
from backend.auth.dependencies import get_current_user
from backend.auth.models import User
from backend.chat.schemas import (
    ChatMessageOut,
    ChatSessionOut,
    FeedbackUpdate,
    SessionRenameRequest,
    TraceOut,
    UsageOut,
)
from backend.chat.service import ChatService
from backend.infrastructure.database.session import get_session

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/history", response_model=list[ChatSessionOut])
async def list_sessions(
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await ChatService(session).list(current.id)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: int,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await ChatService(session).delete(session_id, current.id)


@router.get("/sessions/{session_id}", response_model=ChatSessionOut)
async def get_session_detail(
    session_id: int,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await ChatService(session).detail(session_id, current.id)


@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessageOut])
async def get_messages(
    session_id: int,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await ChatService(session).messages(session_id, current.id)


@router.put(
    "/sessions/{session_id}/messages/{message_id}/feedback",
    response_model=ChatMessageOut,
)
async def update_message_feedback(
    session_id: int,
    message_id: int,
    body: FeedbackUpdate,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await ChatService(session).feedback(
        session_id, message_id, current.id, body.feedback
    )


@router.get("/sessions/{session_id}/trace", response_model=TraceOut)
async def get_session_trace(
    session_id: int,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await ChatService(session).trace(session_id, current.id)


@router.get("/sessions/{session_id}/usage", response_model=UsageOut)
async def get_session_usage(
    session_id: int,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await ChatService(session).usage(session_id, current.id)


@router.patch("/sessions/{session_id}", response_model=ChatSessionOut)
async def rename_session(
    session_id: int,
    body: SessionRenameRequest,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await ChatService(session).rename(session_id, current.id, body.title)


@router.get("/sessions/{session_id}/export", response_class=MarkdownResponse)
async def export_session(
    session_id: int,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return MarkdownResponse(
        await ChatService(session).export(session_id, current.id),
        headers={
            "Content-Disposition": f'attachment; filename="mmrag_session_{session_id}.md"'
        },
    )
