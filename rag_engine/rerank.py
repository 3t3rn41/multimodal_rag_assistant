"""Second-stage reranking interfaces and the BGE CrossEncoder adapter."""

from __future__ import annotations

from dataclasses import replace
from typing import Protocol, Sequence

from .models import RetrievalCandidate


class Reranker(Protocol):
    def rerank(
        self,
        query: str,
        candidates: Sequence[RetrievalCandidate],
        *,
        top_k: int = 8,
    ) -> list[RetrievalCandidate]: ...


class NoOpReranker:
    """Keep fused ordering when an external reranker is not configured."""

    def rerank(
        self,
        query: str,
        candidates: Sequence[RetrievalCandidate],
        *,
        top_k: int = 8,
    ) -> list[RetrievalCandidate]:
        del query
        return [replace(item, rank=rank) for rank, item in enumerate(candidates[:top_k], start=1)]


class CrossEncoderReranker:
    """Use ``BAAI/bge-reranker-v2-m3`` through Sentence Transformers.

    The model is loaded lazily by the constructor. Install the optional
    ``rerank`` extra before creating this class in a worker process.
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-v2-m3",
        *,
        device: str | None = None,
        batch_size: int = 16,
    ) -> None:
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:  # pragma: no cover - depends on optional package
            raise RuntimeError(
                "CrossEncoderReranker requires the optional dependency "
                "sentence-transformers; install multimodal-rag-assistant[rerank]"
            ) from exc
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        self.model_name = model_name
        self.batch_size = batch_size
        self.model = CrossEncoder(model_name, device=device)

    def rerank(
        self,
        query: str,
        candidates: Sequence[RetrievalCandidate],
        *,
        top_k: int = 8,
    ) -> list[RetrievalCandidate]:
        if top_k <= 0 or not candidates:
            return []
        selected = list(candidates)
        pairs = [(query, candidate.chunk.content) for candidate in selected]
        scores = self.model.predict(
            pairs,
            batch_size=self.batch_size,
            show_progress_bar=False,
        )
        reranked = [
            replace(candidate, rerank_score=float(score), score=float(score))
            for candidate, score in zip(selected, scores, strict=True)
        ]
        reranked.sort(key=lambda item: (-float(item.rerank_score or 0.0), item.chunk_id))
        return [replace(item, rank=rank) for rank, item in enumerate(reranked[:top_k], start=1)]
