"""对话（chat）与会话（sessions）相关请求/响应模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.chat.models import MessageRole, SessionMode, SessionStatus
from backend.core.schemas import APIModel


class ChatRequest(BaseModel):
    """发起一轮问答；kb_ids 是经过权限检查的检索范围。"""

    question: str = Field(min_length=1, max_length=4000)
    kb_ids: list[int] = Field(
        min_length=1,
        max_length=1,
        description="会话绑定的唯一知识库，列表必须恰好包含一个 ID",
    )
    session_id: int | None = Field(default=None, description="续接已有会话（多轮）")


class ChatSessionOut(APIModel):
    """会话视图（列表/详情共用）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    mode: SessionMode
    status: SessionStatus
    title: str | None = None
    token_used: int
    cost: float
    kb_ids: list[int] = []
    created_time: datetime


class SessionRenameRequest(BaseModel):
    """会话重命名（管理闭环 12.3.3）：只改 title。"""

    title: str = Field(min_length=1, max_length=200, description="新标题（1-200 字）")


class ChatMessageOut(APIModel):
    """会话消息视图（历史回放用，PRD §23.3）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    role: MessageRole
    content: str | None = None
    refs: list | None = None
    feedback: str | None = None
    created_time: datetime


class FeedbackUpdate(BaseModel):
    """消息反馈：up / down，null 表示取消。"""

    feedback: Literal["up", "down"] | None = None


class TraceTurnOut(APIModel):
    message_id: int | None = None
    created_at: datetime
    metrics: dict = Field(default_factory=dict)
    steps: list[dict] = Field(default_factory=list)


class TraceOut(APIModel):
    session_id: int
    mode: SessionMode
    turns: list[TraceTurnOut]


class UsageTurnOut(APIModel):
    message_id: int | None = None
    created_at: datetime
    metrics: dict = Field(default_factory=dict)


class UsageOut(APIModel):
    session_id: int
    mode: SessionMode
    created_time: datetime
    total_tokens: int
    cost: float
    message_count: int
    turn_count: int
    turns: list[UsageTurnOut]


class AbortOut(APIModel):
    aborted: bool
    session_id: int
