"""上传入口：保存原文件和文档记录，交由任务服务投递解析任务。"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Protocol

from backend.core.errors import ServiceError
from backend.infrastructure.jina.configuration import embedding_configuration
from backend.cleanup.repository import CleanupRepository, utcnow
from backend.infrastructure.storage import (
    BUCKET,
    download_bytes,
    ensure_bucket,
    get_minio_client,
    preview_url,
    upload_bytes,
)
from backend.task.service import TaskService
from backend.upload.models import Document, DocumentFormat, ParseStatus
from backend.upload.document_text import read_document_bytes
from backend.upload.repository import FileRepository
from rag_engine.models import Chunk

from .errors import EmptyFileError, FileTooLargeError, UnsupportedFormatError
from .fetcher import fetch, is_arxiv_url


class IncomingFile(Protocol):
    filename: str | None
    content_type: str | None
    size: int | None

    async def read(self) -> bytes: ...


_EXT_MAP = {
    ".pdf": DocumentFormat.PDF,
    ".docx": DocumentFormat.DOCX,
    ".txt": DocumentFormat.TXT,
    ".md": DocumentFormat.MD,
}
MAX_UPLOAD_BYTES = 100 * 1024 * 1024


def detect_format(filename: str) -> DocumentFormat:
    ext = os.path.splitext(filename)[1].lower()
    fmt = _EXT_MAP.get(ext)
    if fmt is None:
        raise UnsupportedFormatError(
            f"不支持的文件格式: {ext or '(无扩展名)'}"
            "（当前支持 pdf/docx/txt/md，优先使用包含可选中文字的 PDF）"
        )
    return fmt


def _sanitize(filename: str) -> str:
    """清洗文件名：只保留字母数字点横杠下划线中文，防路径穿越。"""
    name = os.path.basename(filename)
    return re.sub(r"[^\w.\-一-鿿]", "_", name) or "file"


logger = logging.getLogger(__name__)


class UploadService:
    def __init__(self, db):
        self.repo = FileRepository(db)
        self.tasks = TaskService(db)

    async def _store_document(
        self,
        content: bytes,
        filename: str,
        fmt: DocumentFormat,
        owner_id: int,
        content_type: str = "application/octet-stream",
        extra_meta: dict | None = None,
    ) -> Document:
        """公共落库流程：建记录 -> 存 MinIO -> commit -> 投递 Celery 任务。"""
        embedding_configuration()  # Validate indexing configuration before any write.
        repo = self.repo
        doc = Document(
            owner_id=owner_id,
            file_name=filename,
            storage_path="",  # 占位，flush 后用 id 拼
            file_type=fmt,
            status=ParseStatus.PENDING,
            file_size=len(content),
        )
        if extra_meta:
            doc.meta = extra_meta
        await repo.create(doc)

        file_key = f"docs/{owner_id}/{doc.id}/{_sanitize(filename)}"
        client = get_minio_client()
        await asyncio.to_thread(ensure_bucket, client)
        await asyncio.to_thread(upload_bytes, client, file_key, content, content_type)
        doc.storage_path = file_key
        doc.meta = {**(doc.meta or {}), "storage_bucket": BUCKET}
        await repo.commit()
        await repo.refresh(doc)

        return await self.tasks.enqueue_document(doc.id)

    async def upload_document(
        self,
        file: IncomingFile,
        owner_id: int,
    ) -> Document:
        """上传文件：存 MinIO + 写 DB + 投递 Celery 任务。返回 Document（status=pending）。"""
        filename = file.filename or "untitled"
        fmt = detect_format(filename)
        if file.size is not None and file.size > MAX_UPLOAD_BYTES:
            raise FileTooLargeError(MAX_UPLOAD_BYTES)
        content = await file.read()
        if not content:
            raise EmptyFileError()
        if len(content) > MAX_UPLOAD_BYTES:
            raise FileTooLargeError(MAX_UPLOAD_BYTES)
        return await self._store_document(
            content,
            filename,
            fmt,
            owner_id,
            file.content_type or "application/octet-stream",
        )

    async def upload_from_url(
        self,
        url: str,
        owner_id: int,
    ) -> Document:
        """从 URL 抓取文档入库。仅接收 arXiv / PDF 链接。

        抓取含 SSRF 防护（禁内网 IP）+ 超时 30s + > 50MB 拒绝（见 fetcher）。
        """
        content, content_type, filename, fetch_meta = await asyncio.to_thread(
            fetch, url
        )
        if not content:
            raise EmptyFileError()
        if len(content) > MAX_UPLOAD_BYTES:
            raise FileTooLargeError(MAX_UPLOAD_BYTES)
        # arXiv 或 PDF 响应类型允许导入；其他内容拒绝。
        if is_arxiv_url(url) or "pdf" in content_type.lower():
            fmt = DocumentFormat.PDF
        else:
            raise UnsupportedFormatError(
                "第二阶段 URL 导入仅支持 PDF，网页正文解析尚未接入。"
            )
        return await self._store_document(
            content, filename, fmt, owner_id, content_type, extra_meta=fetch_meta
        )

    async def owned_document(self, file_id, owner_id, *, lock=False, include_deleted=False):
        doc = await self.repo.get(file_id, lock=lock)
        if (doc is None or doc.owner_id != owner_id
                or (doc.deleted_at is not None and not include_deleted)):
            raise ServiceError("文档不存在。", 404)
        return doc

    async def original_content(self, file_id, owner_id):
        from minio.error import S3Error

        doc = await self.owned_document(file_id, owner_id)
        try:
            content = await asyncio.to_thread(
                download_bytes, get_minio_client(timeout=30), doc.storage_path,
                bucket=(doc.meta or {}).get("storage_bucket") or BUCKET,
            )
        except S3Error as exc:
            if exc.code in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
                raise ServiceError("原文件不存在。", 404) from exc
            logger.warning("original read failed file=%s error_type=%s", file_id, type(exc).__name__)
            raise ServiceError("原文件暂时无法读取，请稍后重试。", 503) from exc
        except Exception as exc:
            logger.warning("original read failed file=%s error_type=%s", file_id, type(exc).__name__)
            raise ServiceError("原文件暂时无法读取，请稍后重试。", 503) from exc
        # Use a current read so a deletion committed during download invalidates it.
        doc = await self.owned_document(file_id, owner_id, lock=True)
        return doc, content

    @staticmethod
    def chunk_view(row, doc):
        return {
            "chunk_id": row.chunk_id,
            "file_id": str(doc.id),
            "generation": row.generation,
            "source_type": row.source_type,
            "time_start": row.time_start,
            "time_end": row.time_end,
            "media_path": row.payload.get("media_path"),
            "file_name": doc.file_name,
            "file_type": doc.file_type.value,
            "content": row.payload.get("content", ""),
            "page": row.payload.get("page"),
            "extra": row.payload.get("extra", {}),
        }

    async def chunks(self, file_id, owner_id):
        doc = await self.owned_document(file_id, owner_id)
        rows = await self.repo.chunks(file_id, doc.version)
        return [
            {
                **self.chunk_view(row, doc),
                "seq": seq,
                "section_path": row.payload.get("extra", {}).get("section_path"),
                "extra": {
                    **row.payload.get("extra", {}),
                    "page": row.payload.get("page"),
                },
            }
            for seq, row in enumerate(rows)
        ]

    async def preview_chunk(self, chunk_id, owner_id):
        row = await self.repo.chunk(chunk_id)
        if row is None:
            raise ServiceError("引用切片不存在。", 404)
        doc = await self.owned_document(row.file_id, owner_id)
        url = await asyncio.to_thread(preview_url, doc.storage_path)
        return {
            **self.chunk_view(row, doc), "preview_url": url,
            "pdf_url": url if doc.file_type == DocumentFormat.PDF else None,
        }

    async def source_chunk(self, chunk_id: str, owner_id: int):
        row = await self.repo.chunk(chunk_id)
        if row is None:
            raise ServiceError("引用切片不存在。", 404)
        doc, raw = await self.original_content(row.file_id, owner_id)
        try:
            source = await asyncio.to_thread(read_document_bytes, raw, doc.file_type.value)
        except Exception as exc:
            logger.warning("source parsing unavailable file=%s error_type=%s", doc.id, type(exc).__name__)
            raise ServiceError("文档正文暂时无法读取，请稍后重试。", 503) from exc
        # A cleanup may have removed this generation while the original was read.
        current = await self.repo.chunk(chunk_id, lock=True)
        if current is None:
            raise ServiceError("引用切片不存在。", 404)
        rows = await self.repo.chunks(doc.id, current.generation)
        chunks = [Chunk.from_payload(item.payload) for item in rows]
        return {
            **self.chunk_view(current, doc),
            "blocks": source.blocks,
            "locations": source.locations(chunks),
            "contents": {chunk.chunk_id: chunk.content for chunk in chunks},
            "original_url": f"/api/files/{doc.id}/content",
        }

    async def reparse(self, file_id, owner_id):
        doc = await self.owned_document(file_id, owner_id)
        return await self.tasks.enqueue_document(doc.id, reparse=True)

    async def prepare_deletion(self, doc):
        """Stage deletion in the caller's locked transaction without committing."""
        now = utcnow()
        doc.deleted_at = doc.deleted_at or now
        tasks = await self.tasks.cancel_for_file(doc.id, now)
        await self.repo.unlink(doc.id)
        job = await CleanupRepository(self.repo.db).for_deleted_file(doc)
        return job, tasks

    async def dispatch_cleanup(self, tasks):
        """Publish after commit; the scheduler recovers unavailable dispatch."""
        await self.tasks.revoke(tasks)
        # Publishing can fail without losing the committed cleanup outbox row.
        from backend.cleanup.dispatch import dispatch_due
        try:
            await asyncio.to_thread(dispatch_due)
        except Exception as exc:
            logger.warning("cleanup dispatch unavailable error_type=%s", type(exc).__name__)

