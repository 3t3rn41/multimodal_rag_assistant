"""knowledge_bases / kb_documents 表 ORM 模型（对齐 PRD §13）。

- knowledge_bases：用户的知识库。一个库归属一个用户，库内挂多篇文档。
- kb_documents：知识库与文档的多对多关联表，带 enabled 开关（禁用的文档不参与检索）。
  (kb_id, file_id) 唯一约束保证同一文档不重复归入同一库。
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.infrastructure.database.base import Base


class Visibility(str, enum.Enum):
    """知识库可见性。M1 先用 private，public 预留给未来可能的分享场景。"""

    PRIVATE = "private"
    PUBLIC = "public"


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    owner_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    topic_tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    visibility: Mapped[Visibility] = mapped_column(
        Enum(Visibility, name="kb_visibility"),
        nullable=False,
        default=Visibility.PRIVATE,
        server_default="private",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<KnowledgeBase id={self.id} name={self.name!r}>"


class KBDocument(Base):
    """知识库-文档关联表，带文档级 enabled 开关与纠错计数。"""

    __tablename__ = "kb_documents"
    __table_args__ = (
        # 同一文档在同一库内只归一次
        UniqueConstraint("kb_id", "file_id", name="uq_kb_documents_kb_file"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    kb_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("knowledge_bases.id"), nullable=False, index=True
    )
    file_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("file_metadata.id"), nullable=False, index=True
    )
    # 文档级开关：禁用的文档不参与检索（PRD §6.2）
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    correction_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<KBDocument kb_id={self.kb_id} doc_id={self.file_id} enabled={self.enabled}>"
