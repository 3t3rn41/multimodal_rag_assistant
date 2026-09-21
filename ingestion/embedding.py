"""Embedding and vector-store handoff shared with member C's retrievers."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any, Protocol
from uuid import UUID

from rag_engine.models import Chunk


class EmbeddingProvider(Protocol):
    """Minimal batch interface for local or hosted embedding services."""

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...


class ChunkEmbeddingProvider(EmbeddingProvider, Protocol):
    """Optional richer provider that can embed text and media together."""

    def embed_chunks(self, chunks: Sequence[Chunk]) -> Sequence[Sequence[float]]: ...


class VectorWriter(Protocol):
    """Storage boundary implemented by Qdrant or a test double."""

    def upsert(self, chunks: Sequence[Chunk]) -> int | None: ...


@dataclass(frozen=True, slots=True)
class IndexingReport:
    """Auditable counts for resumable vector indexing."""

    total: int
    skipped: int
    embedded: int
    upserted: int


def embed_chunks(
    chunks: Sequence[Chunk],
    provider: EmbeddingProvider,
    *,
    batch_size: int = 64,
) -> list[Chunk]:
    """Return immutable copies of chunks with validated embedding vectors."""

    if batch_size <= 0:
        raise ValueError("batch_size must be positive")

    embedded: list[Chunk] = []
    expected_dimension: int | None = None
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        chunk_method = getattr(provider, "embed_chunks", None)
        if callable(chunk_method):
            vectors = list(chunk_method(batch))
        else:
            vectors = list(provider.embed([chunk.content for chunk in batch]))
        if len(vectors) != len(batch):
            raise ValueError(
                "embedding provider returned a different number of vectors "
                f"({len(vectors)}) than inputs ({len(batch)})"
            )
        for chunk, vector in zip(batch, vectors):
            normalized = _normalize_vector(vector)
            if expected_dimension is None:
                expected_dimension = len(normalized)
            elif len(normalized) != expected_dimension:
                raise ValueError("embedding vectors must have the same dimension")
            embedded.append(replace(chunk, embedding=normalized))
    return embedded


def embed_and_upsert(
    chunks: Sequence[Chunk],
    provider: EmbeddingProvider,
    writer: VectorWriter,
    *,
    batch_size: int = 64,
) -> int:
    """Embed chunks and write them in bounded batches; return accepted count."""

    embedded = embed_chunks(chunks, provider, batch_size=batch_size)
    accepted = 0
    for start in range(0, len(embedded), batch_size):
        batch = tuple(embedded[start : start + batch_size])
        writer.upsert(batch)
        accepted += len(batch)
    return accepted


def index_chunks(
    chunks: Sequence[Chunk],
    provider: EmbeddingProvider,
    writer: VectorWriter,
    *,
    batch_size: int = 64,
) -> IndexingReport:
    """Resume an interrupted job and verify every source chunk is present."""

    existing_method = getattr(writer, "existing_chunk_ids", None)
    if not callable(existing_method):
        raise TypeError("resumable indexing requires writer.existing_chunk_ids")

    existing = set(existing_method(chunks))
    pending = [chunk for chunk in chunks if chunk.chunk_id not in existing]
    embedded = embed_chunks(pending, provider, batch_size=batch_size)
    upserted = 0
    for start in range(0, len(embedded), batch_size):
        batch = tuple(embedded[start : start + batch_size])
        result = writer.upsert(batch)
        upserted += len(batch) if result is None else int(result)

    confirmed = set(existing_method(chunks))
    expected = {chunk.chunk_id for chunk in chunks}
    missing = sorted(expected - confirmed)
    if missing:
        preview = ", ".join(missing[:5])
        raise RuntimeError(
            "vector consistency check failed; missing chunk IDs: " + preview
        )
    return IndexingReport(
        total=len(chunks),
        skipped=len(existing),
        embedded=len(pending),
        upserted=upserted,
    )


class QdrantVectorWriter:
    """Write C-compatible chunk payloads to a Qdrant collection.

    ``qdrant-client`` is imported only when a writer is used, keeping local
    ingestion tests and BM25 development dependency-free.
    """

    def __init__(
        self,
        client: Any,
        collection_name: str,
        *,
        vector_name: str | None = None,
        wait: bool = True,
    ) -> None:
        self.client = client
        self.collection_name = collection_name
        self.vector_name = vector_name
        self.wait = wait

    def upsert(self, chunks: Sequence[Chunk]) -> int:
        try:
            from qdrant_client.models import PointStruct
        except ImportError as exc:  # pragma: no cover - optional integration
            raise RuntimeError(
                "QdrantVectorWriter requires the 'qdrant' optional dependency"
            ) from exc

        points = []
        for chunk in chunks:
            if chunk.embedding is None:
                raise ValueError(f"chunk {chunk.chunk_id!r} has no embedding")
            vector: list[float] | dict[str, list[float]]
            values = list(chunk.embedding)
            vector = values if self.vector_name is None else {self.vector_name: values}
            points.append(
                PointStruct(
                    id=_qdrant_point_id(chunk),
                    vector=vector,
                    payload=chunk.to_payload(),
                )
            )
        self.client.upsert(
            collection_name=self.collection_name,
            points=points,
            wait=self.wait,
        )
        return len(points)

    def existing_chunk_ids(self, chunks: Sequence[Chunk]) -> set[str]:
        """Return source IDs already present in Qdrant for resume support."""

        if not chunks:
            return set()
        points = self.client.retrieve(
            collection_name=self.collection_name,
            ids=[_qdrant_point_id(chunk) for chunk in chunks],
            with_payload=True,
            with_vectors=False,
        )
        existing: set[str] = set()
        for point in points:
            payload = dict(getattr(point, "payload", None) or {})
            chunk_id = payload.get("chunk_id")
            if chunk_id:
                existing.add(str(chunk_id))
        return existing


def _normalize_vector(vector: Sequence[float]) -> tuple[float, ...]:
    try:
        normalized = tuple(float(value) for value in vector)
    except (TypeError, ValueError) as exc:
        raise ValueError("embedding vectors must contain numeric values") from exc
    if not normalized:
        raise ValueError("embedding vectors must not be empty")
    if not all(math.isfinite(value) for value in normalized):
        raise ValueError("embedding vectors must contain finite values")
    return normalized


def _qdrant_point_id(chunk: Chunk) -> str:
    """Return the persisted Qdrant UUID without deriving one from chunk text.

    The ingestion layer assigns a random UUID4 and stores it in the chunk
    payload. Arbitrary IDs must fail here instead of being converted through a
    hash, which would violate the project's no-hash constraint and could make
    a resumed index depend on an implicit identifier scheme.
    """

    candidate = chunk.extra.get("qdrant_point_id")
    if candidate is None:
        candidate = chunk.chunk_id
    try:
        return str(UUID(str(candidate)))
    except (AttributeError, ValueError, TypeError) as exc:
        raise ValueError(
            f"chunk {chunk.chunk_id!r} requires a persisted UUID in "
            "extra['qdrant_point_id'] or UUID chunk_id"
        ) from exc
