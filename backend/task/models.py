"""The durable ingestion task ledger, including phase and indexing statistics."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.infrastructure.database.base import Base


class IngestionTask(Base):
    __tablename__ = "task"
    __table_args__ = (Index("ix_task_doc_generation", "file_id", "generation"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    file_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("file_metadata.id"), nullable=False
    )
    task_type: Mapped[str] = mapped_column(
        String(24), nullable=False, default="document", server_default="document"
    )
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="PENDING", server_default="PENDING"
    )
    sub_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="QUEUED", server_default="QUEUED"
    )
    progress: Mapped[float] = mapped_column(
        Float, nullable=False, default=0, server_default="0"
    )
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    failed_stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    stage_metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    indexing_report: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    configuration_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, onupdate=func.now(), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
