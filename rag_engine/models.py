"""Domain objects shared by ingestion, retrieval, generation, and UI layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class Chunk:
    """A normalized multimodal chunk following the project data contract."""

    chunk_id: str
    file_id: str
    source_type: str
    content: str
    embedding: tuple[float, ...] | None = None
    time_start: float | None = None
    time_end: float | None = None
    page: int | None = None
    media_path: str | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.chunk_id:
            raise ValueError("chunk_id must not be empty")
        if not self.file_id:
            raise ValueError("file_id must not be empty")
        if not self.source_type:
            raise ValueError("source_type must not be empty")

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any], *, fallback_id: str | None = None) -> "Chunk":
        """Build a chunk from a vector-store payload.

        Some stores nest application metadata under ``metadata``. Supporting both
        shapes keeps the adapter compatible with existing collections.
        """

        data: Mapping[str, Any] = payload.get("metadata", payload)
        chunk_id = str(data.get("chunk_id") or fallback_id or "")
        return cls(
            chunk_id=chunk_id,
            file_id=str(data.get("file_id", "unknown")),
            source_type=str(data.get("source_type", "document")),
            content=str(data.get("content", "")),
            embedding=tuple(data["embedding"]) if data.get("embedding") else None,
            time_start=_as_float(data.get("time_start")),
            time_end=_as_float(data.get("time_end")),
            page=_as_int(data.get("page")),
            media_path=data.get("media_path"),
            extra=dict(data.get("extra") or {}),
        )

    def to_payload(self, *, include_embedding: bool = False) -> dict[str, Any]:
        """Serialize the chunk for storage or API responses."""

        payload: dict[str, Any] = {
            "chunk_id": self.chunk_id,
            "file_id": self.file_id,
            "source_type": self.source_type,
            "content": self.content,
            "time_start": self.time_start,
            "time_end": self.time_end,
            "page": self.page,
            "media_path": self.media_path,
            "extra": dict(self.extra),
        }
        if include_embedding and self.embedding is not None:
            payload["embedding"] = list(self.embedding)
        return payload


@dataclass(slots=True)
class RetrievalCandidate:
    """A chunk returned by one or more retrieval stages."""

    chunk: Chunk
    score: float
    source: str
    rank: int = 0
    raw_score: float | None = None
    fused_score: float | None = None
    rerank_score: float | None = None

    @property
    def chunk_id(self) -> str:
        return self.chunk.chunk_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "file_id": self.chunk.file_id,
            "source_type": self.chunk.source_type,
            "score": self.score,
            "source": self.source,
            "rank": self.rank,
            "raw_score": self.raw_score,
            "fused_score": self.fused_score,
            "rerank_score": self.rerank_score,
        }


@dataclass(frozen=True, slots=True)
class Citation:
    """A safe, renderable reference to a retrieved chunk."""

    chunk_id: str
    file_id: str
    source_type: str
    label: str
    page: int | None = None
    time_start: float | None = None
    time_end: float | None = None
    media_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "file_id": self.file_id,
            "source_type": self.source_type,
            "label": self.label,
            "page": self.page,
            "time_start": self.time_start,
            "time_end": self.time_end,
            "media_path": self.media_path,
        }


def _as_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _as_int(value: Any) -> int | None:
    return None if value is None else int(value)
