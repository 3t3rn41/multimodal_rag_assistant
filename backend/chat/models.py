"""问答会话、知识库范围、消息与每轮检索/生成轨迹。"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.infrastructure.database.base import Base


def _values(enum_cls):
    """Enum 列按成员的 value（小写）落库，与迁移脚本/前端约定一致。

    坑：SQLAlchemy 的 Enum(SomeEnum) 默认按成员 **名**（CHAT）存取，
    而 M2 迁移建的是值枚举（'chat'）。MySQL ENUM 大小写不敏感会把 'CHAT' 归一成
    'chat'，读回时按名查找直接 LookupError。必须 values_callable 显式对齐。
    """
    return [m.value for m in enum_cls]


class SessionMode(str, enum.Enum):
    """文档问答会话。"""

    CHAT = "chat"


class SessionStatus(str, enum.Enum):
    """会话状态机：executing -> done | aborted | error。"""

    EXECUTING = "executing"
    DONE = "done"
    ABORTED = "aborted"
    ERROR = "error"


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class Session(Base):
    __tablename__ = "chat_session"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id"), nullable=False, index=True
    )
    mode: Mapped[SessionMode] = mapped_column(
        Enum(SessionMode, name="session_mode", values_callable=_values),
        nullable=False,
        default=SessionMode.CHAT,
        server_default="chat",
    )
    token_used: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    cost: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0"
    )
    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus, name="session_status", values_callable=_values),
        nullable=False,
        default=SessionStatus.EXECUTING,
        server_default="executing",
    )
    # 首个用户问题，列表页展示用
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_time: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=True
    )

    def __repr__(self) -> str:
        return f"<Session id={self.id} mode={self.mode} status={self.status}>"


class SessionScope(Base):
    """会话首次创建时绑定的唯一知识库，续聊不能修改。"""

    __tablename__ = "session_scopes"
    __table_args__ = (
        UniqueConstraint("session_id", "kb_id", name="uq_session_scopes_sess_kb"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chat_session.id"), nullable=False, index=True
    )
    kb_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("knowledge_bases.id"), nullable=False, index=True
    )


class Message(Base):
    __tablename__ = "chat_message"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chat_session.id"), nullable=False, index=True
    )
    role: Mapped[MessageRole] = mapped_column(
        Enum(MessageRole, name="message_role", values_callable=_values), nullable=False
    )
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 该消息引用的 chunk（citation 事件落库）
    refs: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # 用户反馈："up" / "down" / None（未评价）
    feedback: Mapped[str | None] = mapped_column(String(8), nullable=True)
    created_time: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<Message id={self.id} session={self.session_id} role={self.role}>"


class Trace(Base):
    """每轮回答的步骤与指标，关联到 assistant 消息。"""

    __tablename__ = "traces"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chat_session.id"), nullable=False, index=True
    )
    # 该轮 trace 对应的 assistant 消息（12.4.1 轨迹重建：精确配对问答与推理步骤）。
    # 未关联消息的记录不参与历史步骤回放；前端只按 message_id 配对。
    message_id: Mapped[int | None] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("chat_message.id"),
        nullable=True,
        index=True,
    )
    steps: Mapped[list | None] = mapped_column(JSON, nullable=True)
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
