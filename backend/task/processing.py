"""Document processing, durable progress and indexing through Member B modules."""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.infrastructure.database.session import SyncSessionLocal
from backend.infrastructure.jina.configuration import (
    JinaConfigurationError,
    embedding_from_snapshot,
    jina_profile,
)
from backend.infrastructure.jina.embedding import build_embedder
from backend.infrastructure.qdrant import get_client
from backend.infrastructure.storage import download_bytes, get_minio_client
from backend.task.errors import (
    EmptyDocumentError,
    IngestionConfigurationError,
    StaleIngestionTask,
)
from backend.upload.models import Document, DocumentFormat, ParseStatus, RagChunk
from backend.upload.document_text import DOCUMENT_MAX_CHARS, DOCUMENT_OVERLAP_CHARS, read_document
from ingestion import (
    MultimodalEmbeddingAPIConfig,
    QdrantVectorWriter,
    chunk_document,
    ensure_qdrant_collection,
    index_chunks,
)
from ingestion.retry import RetryPolicy
from rag_engine.models import Chunk

from .models import IngestionTask
from .progress import file_task_metadata, update_metrics
from .repository import WorkerRepository


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _current(session, task_id: str) -> tuple[IngestionTask, Document]:
    task, doc = WorkerRepository(session).current(task_id)
    if task is None:
        raise StaleIngestionTask()
    if (
        doc is None
        or doc.deleted_at is not None
        or doc.version != task.generation
        or (doc.meta or {}).get("task_id") != task_id
    ):
        raise StaleIngestionTask()
    return task, doc


def _update(
    task_id: str,
    *,
    stage: str,
    progress: float,
    status: str = "PROCESSING",
    error: str | None = None,
    metrics_completed: int | None = None,
    metrics_total: int | None = None,
    indexing_report: dict | None = None,
    **metadata,
) -> None:
    with SyncSessionLocal() as session:
        task, doc = _current(session, task_id)
        task.status = status
        task.sub_status = stage
        task.progress = max(task.progress, max(0.0, min(100.0, float(progress))))
        task.error_msg = error
        task.updated_at = _utcnow()
        if indexing_report is not None:
            task.indexing_report = indexing_report
        update_metrics(task, stage, status, task.updated_at, completed=metrics_completed, total=metrics_total)
        if status == "PROCESSING" and task.started_at is None:
            task.started_at = _utcnow()
        if status in {"SUCCESS", "FAILED"}:
            task.completed_at = _utcnow()
        doc.status = {
            "SUCCESS": ParseStatus.DONE,
            "FAILED": ParseStatus.FAILED,
        }.get(status, ParseStatus.PARSING)
        doc.meta = {
            **(doc.meta or {}),
            **metadata,
            **file_task_metadata(task),
        }
        if status == "SUCCESS":
            from backend.cleanup.repository import schedule_superseded
            schedule_superseded(session, doc)
        WorkerRepository(session).commit()


def _load_or_parse(task_id: str, lease) -> list[Chunk]:
    with SyncSessionLocal() as session:
        task, doc = _current(session, task_id)
        doc_id, generation, owner_id, title, file_key = (
            doc.id,
            task.generation,
            doc.owner_id,
            doc.file_name,
            doc.storage_path,
        )
        saved = WorkerRepository(session).chunks(doc_id, generation)
        if saved:
            return [Chunk.from_payload(row.payload) for row in saved]
        file_format = getattr(doc.file_type, "value", str(doc.file_type)).lower()
        snapshot = task.configuration_snapshot or {}
    if file_format not in {kind.value for kind in DocumentFormat}:
        raise IngestionConfigurationError(
            "当前网页接通 PDF、DOCX、TXT、MD；请选择其中一种文件。"
        )
    _update(task_id, stage="PARSING", progress=10, metrics_completed=0, metrics_total=1)
    raw = download_bytes(get_minio_client(), file_key)
    with TemporaryDirectory(prefix="mmrag-ingest-") as directory:
        path = Path(directory) / f"source.{file_format}"
        path.write_bytes(raw)
        source = read_document(path)
        parsed = source.parsed
    if not parsed.blocks:
        message = "文件未提取到可检索文字，请检查文档是否包含有效正文。"
        if file_format == "pdf":
            message += "扫描版 PDF 尚未接通 OCR，请使用包含可选中文字的 PDF。"
        raise EmptyDocumentError(message)
    _refresh_lease(lease)
    _update(task_id, stage="PARSING", progress=25, metrics_completed=1, metrics_total=1)
    _update(task_id, stage="SLICING", progress=30, metrics_completed=0, metrics_total=1)
    chunks = source.annotate(chunk_document(
        str(doc_id), parsed.blocks,
        max_chars=DOCUMENT_MAX_CHARS, overlap_chars=DOCUMENT_OVERLAP_CHARS,
    ))
    if not chunks:
        raise EmptyDocumentError("文件解析后没有有效切片，请检查文档是否包含文字。")
    chunks = [
        replace(
            chunk,
            chunk_id=f"{doc_id}:g{generation}:{chunk.chunk_id.split(':', 1)[1]}",
            extra={
                **dict(chunk.extra),
                "doc_id": doc_id,
                "owner_id": owner_id,
                "file_name": title,
                "generation": generation,
                **(
                    {
                        "embedding_space": snapshot["embedding_space"],
                        "vector_collection": snapshot["vector_collection"],
                    }
                    if snapshot.get("embedding_space")
                    else {}
                ),
            },
        )
        for chunk in chunks
    ]
    with SyncSessionLocal() as session:
        _, doc = _current(session, task_id)
        repo = WorkerRepository(session)
        for chunk in chunks:
            repo.add(
                RagChunk(
                    chunk_id=chunk.chunk_id,
                    file_id=doc_id,
                    generation=generation,
                    payload=chunk.to_payload(),
                )
            )
        doc.meta = {
            **(doc.meta or {}),
            "chunk_count": len(chunks),
            "page_count": max((block.page or 0 for block in parsed.blocks), default=0),
            "adapter_fallback": any(
                block.extra.get("adapter_fallback") for block in parsed.blocks
            ),
        }
        repo.commit()
    _update(task_id, stage="SLICING", progress=35, metrics_completed=1, metrics_total=1)
    return chunks


def _vector_writer(
    config: MultimodalEmbeddingAPIConfig, collection: str | None = None
) -> QdrantVectorWriter:
    profile = jina_profile()
    if collection and collection != profile["vector_collection"]:
        raise IngestionConfigurationError(
            "任务集合与系统 Jina 配置不一致，请重新处理文档。"
        )
    collection, vector_name = profile["vector_collection"], profile["vector_name"]
    client = get_client(timeout=30)
    try:
        ensure_qdrant_collection(
            client, collection, config.dimensions, vector_name=vector_name
        )
    except Exception:
        client.close()
        raise
    return QdrantVectorWriter(
        client,
        collection,
        vector_name=vector_name,
        retry_policy=RetryPolicy(max_retries=0),
    )


class _ProgressProvider:
    def __init__(self, task_id: str, provider, total: int, lease) -> None:
        self.task_id, self.provider, self.total, self.lease = (
            task_id,
            provider,
            total,
            lease,
        )
        self.completed = 0

    def embed_chunks(self, chunks):
        _refresh_lease(self.lease)
        _update(
            self.task_id,
            stage="EMBEDDING",
            progress=40 + 40 * self.completed / max(1, self.total),
            metrics_completed=self.completed, metrics_total=self.total,
        )
        vectors = self.provider.embed_chunks(chunks)
        self.completed += len(chunks)
        _update(
            self.task_id,
            stage="EMBEDDING",
            progress=40 + 40 * self.completed / max(1, self.total),
            metrics_completed=self.completed, metrics_total=self.total,
        )
        return vectors


class _ProgressWriter:
    def __init__(self, task_id: str, writer, total: int, lease, provider) -> None:
        self.task_id, self.writer, self.total, self.lease = (
            task_id,
            writer,
            total,
            lease,
        )
        self.completed = 0
        self.provider = provider
        self._checked_existing = False

    def existing_chunk_ids(self, chunks):
        _refresh_lease(self.lease)
        with SyncSessionLocal() as session:
            _current(session, self.task_id)
        existing = self.writer.existing_chunk_ids(chunks)
        if not self._checked_existing:
            self._checked_existing = True
            self.total = self.provider.total = len(chunks) - len(existing)
            _update(self.task_id, stage="EMBEDDING", progress=40,
                    metrics_completed=0, metrics_total=self.total)
        return existing

    def upsert(self, chunks):
        _refresh_lease(self.lease)
        _update(
            self.task_id,
            stage="INDEXING",
            progress=80 + 15 * self.completed / max(1, self.total),
            metrics_completed=self.completed, metrics_total=self.total,
        )
        accepted = self.writer.upsert(chunks)
        self.completed += len(chunks)
        _update(
            self.task_id,
            stage="INDEXING",
            progress=80 + 15 * self.completed / max(1, self.total),
            metrics_completed=self.completed, metrics_total=self.total,
        )
        return accepted


def _refresh_lease(lease) -> None:
    if lease is not None:
        lease.reacquire()


def _process_ingestion(task_id: str, lease=None) -> dict:
    with SyncSessionLocal() as session:
        task, doc = _current(session, task_id)
        if task.status == "SUCCESS":
            return {"task_id": task_id, "status": "SUCCESS", "already_done": True}
        snapshot = task.configuration_snapshot
        owner_id = doc.owner_id
    chunks = _load_or_parse(task_id, lease)
    _update(task_id, stage="EMBEDDING", progress=40, metrics_completed=0, metrics_total=len(chunks))
    if snapshot:
        if snapshot.get("user_id") != owner_id:
            raise IngestionConfigurationError("任务配置不属于该文档用户，请重新解析。")
        try:
            config = embedding_from_snapshot(snapshot)
        except JinaConfigurationError as exc:
            raise IngestionConfigurationError(str(exc)) from None
        writer = _vector_writer(config, snapshot["vector_collection"])
    else:
        raise IngestionConfigurationError(
            "任务配置缺失，请在知识库重新解析文件。"
        )
    try:
        provider = _ProgressProvider(
            task_id, build_embedder(config), len(chunks), lease
        )
        progress_writer = _ProgressWriter(task_id, writer, len(chunks), lease, provider)
        report = index_chunks(chunks, provider, progress_writer, batch_size=32)
    finally:
        close = getattr(writer.client, "close", None)
        if callable(close):
            close()
    # A resumed task may skip every point; expose a completed, zero-work index phase.
    _update(task_id, stage="INDEXING", progress=95,
            metrics_completed=report.upserted, metrics_total=report.total - report.skipped)
    _update(
        task_id,
        stage="COMPLETED",
        progress=100,
        status="SUCCESS",
        indexed_count=report.total,
        indexing_report=asdict(report),
    )
    return {"task_id": task_id, "status": "SUCCESS", "chunk_count": report.total}
