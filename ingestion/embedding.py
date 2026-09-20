"""Embedding and vector-store handoff shared with member C's retrievers."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import replace
from typing import Any, Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from rag_engine.models import Chunk


class EmbeddingProvider(Protocol):
    """Minimal batch interface for local or hosted embedding services."""

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...


class VectorWriter(Protocol):
    """Storage boundary implemented by Qdrant or a test double."""

    def upsert(self, chunks: Sequence[Chunk]) -> int | None: ...


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
                    id=_qdrant_point_id(chunk.chunk_id),
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


def _qdrant_point_id(chunk_id: str) -> str:
    try:
        UUID(chunk_id)
    except ValueError:
        return str(uuid5(NAMESPACE_URL, f"multimodal-rag:{chunk_id}"))
    return chunk_id
