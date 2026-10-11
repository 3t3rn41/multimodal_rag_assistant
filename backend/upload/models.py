"""Persisted canonical chunk references for uploaded files."""

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
    Index,
    Integer,
    String,
    event,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.infrastructure.database.base import Base


class RagChunk(Base):
    __tablename__ = "chunk_ref"
    __table_args__ = (Index("ix_chunk_ref_doc_generation", "file_id", "generation"),)

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    chunk_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    file_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("file_metadata.id"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="document"
    )
    time_start: Mapped[float | None] = mapped_column(Float, nullable=True)
    time_end: Mapped[float | None] = mapped_column(Float, nullable=True)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


@event.listens_for(RagChunk, "before_insert")
@event.listens_for(RagChunk, "before_update")
def sync_chunk_columns(mapper, connection, target):
    target.source_type = target.payload.get("source_type", "document")
    target.time_start = target.payload.get("time_start")
    target.time_end = target.payload.get("time_end")


class DocumentFormat(str, enum.Enum):
    """当前网页支持的上传格式。"""

    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"
    MD = "md"


class ParseStatus(str, enum.Enum):
    """文档解析状态机：pending -> parsing -> done | failed。"""

    PENDING = "pending"
    PARSING = "parsing"
    DONE = "done"
    FAILED = "failed"


class Document(Base):
    __tablename__ = "file_metadata"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    owner_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id"), nullable=False, index=True
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # MinIO 对象 key（bucket 内路径），如 "docs/{owner_id}/{doc_id}/original.pdf"
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    file_size: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    file_type: Mapped[DocumentFormat] = mapped_column(
        Enum(DocumentFormat, name="document_format"),
        nullable=False,
    )
    status: Mapped[ParseStatus] = mapped_column(
        Enum(ParseStatus, name="parse_status"),
        nullable=False,
        default=ParseStatus.PENDING,
        server_default="pending",
    )
    # 重试/重处理时递增；检索只选取此版本的 chunk_ref。
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    # 额外元数据：来源 URL、文件大小、页数、structure_quality 等
    # 注意：属性名用 meta，列名 metadata（metadata 是 SQLAlchemy 保留属性，不能直接用作模型属性）
    meta: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    upload_time: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, onupdate=func.now(), nullable=True
    )
    # 软删标记：立即退出检索，原件、向量及切片随后由持久化清理任务回收；
    # 检索作用域、重建脚本、状态查询都按 deleted_at IS NULL 过滤
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, index=True
    )

    def __repr__(self) -> str:
        return (
            f"<Document id={self.id} file_name={self.file_name!r} status={self.status}>"
        )
