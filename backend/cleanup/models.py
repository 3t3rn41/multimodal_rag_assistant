"""Deletion outbox and resumable resource cleanup ledger."""

from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.infrastructure.database.base import Base


class ResourceCleanup(Base):
    __tablename__ = "resource_cleanup"
    __table_args__ = (
        UniqueConstraint("file_id", "kind", "target_generation", name="uq_cleanup_file_kind_generation"),
        Index("ix_cleanup_dispatch", "status", "next_attempt_at", "dispatch_after"),
        Index("ix_cleanup_owner_created", "owner_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("user.id"), nullable=False)
    file_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("file_metadata.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    target_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    object_bucket: Mapped[str | None] = mapped_column(String(128), nullable=True)
    object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    target_results: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING", server_default="PENDING")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    dispatch_after: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    lease_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, onupdate=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
