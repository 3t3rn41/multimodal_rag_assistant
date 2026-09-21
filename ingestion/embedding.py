"""Embedding and vector-store handoff shared with member C's retrievers."""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, Protocol
from uuid import UUID

from rag_engine.models import Chunk

from .retry import RetryPolicy, retry_call


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
        retry_policy: RetryPolicy | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.client = client
        self.collection_name = collection_name
        self.vector_name = vector_name
        self.wait = wait
        self.retry_policy = retry_policy or RetryPolicy()
        self.sleeper = sleeper

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
        retry_call(
            lambda: self.client.upsert(
                collection_name=self.collection_name,
                points=points,
                wait=self.wait,
            ),
            policy=self.retry_policy,
            is_retryable=_is_retryable_qdrant_error,
            sleeper=self.sleeper,
        )
        return len(points)

    def existing_chunk_ids(self, chunks: Sequence[Chunk]) -> set[str]:
        """Return source IDs already present in Qdrant for resume support."""

        if not chunks:
            return set()
        points = retry_call(
            lambda: self.client.retrieve(
                collection_name=self.collection_name,
                ids=[_qdrant_point_id(chunk) for chunk in chunks],
                with_payload=True,
                with_vectors=False,
            ),
            policy=self.retry_policy,
            is_retryable=_is_retryable_qdrant_error,
            sleeper=self.sleeper,
        )
        existing: set[str] = set()
        for point in points:
            payload = dict(getattr(point, "payload", None) or {})
            chunk_id = payload.get("chunk_id")
            if chunk_id:
                existing.add(str(chunk_id))
        return existing


def ensure_qdrant_collection(
    client: Any,
    collection_name: str,
    dimensions: int,
    *,
    vector_name: str | None = None,
    recreate: bool = False,
) -> None:
    """Create a dimension-safe collection for the selected Jina model.

    ``recreate=True`` is intentionally limited to the exact collection name
    supplied by the caller and is used by the full rebuild command. It never
    deletes the previous generic collection unless the caller explicitly
    points at it.
    """

    if not collection_name.strip():
        raise ValueError("collection_name must not be empty")
    if dimensions <= 0:
        raise ValueError("dimensions must be positive")
    try:
        from qdrant_client import models
    except ImportError as exc:  # pragma: no cover - optional integration
        raise RuntimeError(
            "Qdrant collection management requires the 'qdrant' optional dependency"
        ) from exc

    exists = bool(client.collection_exists(collection_name=collection_name))
    if exists and recreate:
        client.delete_collection(collection_name=collection_name)
        exists = False
    if exists:
        _validate_existing_qdrant_schema(
            client,
            collection_name,
            dimensions,
            vector_name=vector_name,
        )
        return

    vector_params = models.VectorParams(
        size=dimensions,
        distance=models.Distance.COSINE,
    )
    vectors_config = (
        {vector_name: vector_params} if vector_name else vector_params
    )
    client.create_collection(
        collection_name=collection_name,
        vectors_config=vectors_config,
    )


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


def _validate_existing_qdrant_schema(
    client: Any,
    collection_name: str,
    dimensions: int,
    *,
    vector_name: str | None,
) -> None:
    info = client.get_collection(collection_name=collection_name)
    try:
        vectors = info.config.params.vectors
    except AttributeError as exc:
        raise ValueError(
            f"Qdrant collection {collection_name!r} has no readable vector schema"
        ) from exc

    if vector_name:
        if not isinstance(vectors, Mapping) or vector_name not in vectors:
            raise ValueError(
                f"Qdrant collection {collection_name!r} has no named vector "
                f"{vector_name!r}"
            )
        vector_params = vectors[vector_name]
    else:
        if isinstance(vectors, Mapping):
            raise ValueError(
                f"Qdrant collection {collection_name!r} uses named vectors; "
                "configure vector_name"
            )
        vector_params = vectors

    actual_dimensions = getattr(vector_params, "size", None)
    if actual_dimensions != dimensions:
        raise ValueError(
            f"Qdrant collection {collection_name!r} dimensions mismatch: "
            f"expected {dimensions}, found {actual_dimensions}"
        )
    actual_distance = getattr(vector_params, "distance", None)
    actual_distance = getattr(actual_distance, "value", actual_distance)
    if str(actual_distance).casefold() != "cosine":
        raise ValueError(
            f"Qdrant collection {collection_name!r} distance mismatch: "
            f"expected cosine, found {actual_distance}"
        )


def _is_retryable_qdrant_error(exc: Exception) -> bool:
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        return True
    status_code = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    if status_code is None and response is not None:
        status_code = getattr(response, "status_code", None)
    return isinstance(status_code, int) and (
        status_code in {408, 425, 429} or status_code >= 500
    )
