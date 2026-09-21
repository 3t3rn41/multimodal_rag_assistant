"""Second-stage reranking interfaces and API-backed Qwen adapters."""

from __future__ import annotations

import math
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from dataclasses import replace
from typing import Any, Protocol

from .models import RetrievalCandidate


class RerankAPIError(RuntimeError):
    """Raised when SiliconFlow returns an invalid rerank response."""


class RerankTransport(Protocol):
    def post_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        payload: dict[str, object],
        timeout: float,
    ) -> Mapping[str, Any]: ...


class HttpxRerankTransport:
    """Lazy HTTP transport so offline retrieval tests need no HTTP package."""

    def post_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        payload: dict[str, object],
        timeout: float,
    ) -> Mapping[str, Any]:
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "SiliconFlow reranking requires the 'api' optional dependency"
            ) from exc
        try:
            response = httpx.post(
                url,
                headers=headers,
                json=payload,
                timeout=timeout,
            )
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise RerankAPIError(f"rerank API request failed: {exc}") from exc
        if not isinstance(data, Mapping):
            raise RerankAPIError("rerank API response must be a JSON object")
        return data


@dataclass(frozen=True, slots=True)
class SiliconFlowRerankConfig:
    """Configuration for SiliconFlow Qwen3-VL-Reranker-8B."""

    url: str = "https://api.siliconflow.cn/v1/rerank"
    api_key: str = ""
    model: str = "Qwen/Qwen3-VL-Reranker-8B"
    timeout_seconds: float = 60.0

    def __post_init__(self) -> None:
        if not self.url.strip():
            raise ValueError("rerank API URL must not be empty")
        if not self.api_key.strip():
            raise ValueError("rerank API key must not be empty")
        if not self.model.strip():
            raise ValueError("rerank model must not be empty")
        if self.timeout_seconds <= 0 or not math.isfinite(self.timeout_seconds):
            raise ValueError("rerank timeout must be a finite positive number")

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
    ) -> "SiliconFlowRerankConfig":
        values = os.environ if env is None else env
        api_key = values.get("RAG_RERANK_API_KEY", "").strip() or values.get(
            "SILICONFLOW_API_KEY", ""
        ).strip()
        if not api_key:
            raise ValueError("RAG_RERANK_API_KEY or SILICONFLOW_API_KEY is required")
        try:
            timeout = float(values.get("RAG_RERANK_TIMEOUT_SECONDS", "60"))
        except ValueError as exc:
            raise ValueError("RAG_RERANK_TIMEOUT_SECONDS must be numeric") from exc
        return cls(
            url=values.get(
                "RAG_RERANK_API_URL",
                "https://api.siliconflow.cn/v1/rerank",
            ),
            api_key=api_key,
            model=values.get(
                "RAG_RERANK_MODEL",
                "Qwen/Qwen3-VL-Reranker-8B",
            ),
            timeout_seconds=timeout,
        )


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


class SiliconFlowReranker:
    """Use SiliconFlow's multimodal Qwen reranker for second-stage ranking.

    SiliconFlow's VL rerank endpoint accepts each document as text or image.
    For image/video chunks this adapter sends the accessible representative
    image; document and audio chunks are sent as text. The embedding stage
    still fuses text and image vectors for those chunks.
    """

    def __init__(
        self,
        config: SiliconFlowRerankConfig,
        *,
        transport: RerankTransport | None = None,
        media_url_resolver: Callable[[str], str | None] | None = None,
    ) -> None:
        self.config = config
        self.transport = transport or HttpxRerankTransport()
        self.media_url_resolver = media_url_resolver

    def rerank(
        self,
        query: str,
        candidates: Sequence[RetrievalCandidate],
        *,
        top_k: int = 8,
    ) -> list[RetrievalCandidate]:
        if top_k <= 0 or not candidates:
            return []
        selected_count = min(top_k, len(candidates))
        documents = [self._document_input(candidate) for candidate in candidates]
        payload: dict[str, object] = {
            "model": self.config.model,
            "query": query,
            "documents": documents,
            "top_n": selected_count,
            "return_documents": False,
        }
        response = self.transport.post_json(
            self.config.url,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            payload=payload,
            timeout=self.config.timeout_seconds,
        )
        ranked = _parse_rerank_results(response, candidate_count=len(candidates))
        ranked.sort(key=lambda item: (-item[1], candidates[item[0]].chunk_id))
        return [
            replace(
                candidates[index],
                rerank_score=score,
                score=score,
                rank=rank,
            )
            for rank, (index, score) in enumerate(ranked[:selected_count], start=1)
        ]

    def _document_input(self, candidate: RetrievalCandidate) -> dict[str, str]:
        media_url = self._media_url(candidate)
        if media_url is not None:
            return {"image": media_url}
        if not candidate.chunk.content.strip():
            raise ValueError(f"chunk {candidate.chunk_id!r} has no rerank content")
        return {"text": candidate.chunk.content}

    def _media_url(self, candidate: RetrievalCandidate) -> str | None:
        chunk = candidate.chunk
        if chunk.source_type not in {"image", "video"} or not chunk.media_path:
            return None
        value = chunk.media_path
        if self.media_url_resolver is not None:
            value = self.media_url_resolver(value) or ""
        if value.startswith(("https://", "http://", "data:")):
            return value
        return None


def _parse_rerank_results(
    response: Mapping[str, Any],
    *,
    candidate_count: int,
) -> list[tuple[int, float]]:
    results = response.get("results")
    if not isinstance(results, list) or not results:
        raise RerankAPIError("rerank API response is missing results")
    parsed: list[tuple[int, float]] = []
    seen: set[int] = set()
    for row in results:
        if not isinstance(row, Mapping):
            raise RerankAPIError("rerank API result entries must be objects")
        try:
            index = int(row["index"])
            score = float(row["relevance_score"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RerankAPIError("rerank API result is missing index or score") from exc
        if index < 0 or index >= candidate_count:
            raise RerankAPIError("rerank API returned an out-of-range index")
        if index in seen:
            raise RerankAPIError("rerank API returned duplicate indices")
        if not math.isfinite(score):
            raise RerankAPIError("rerank API returned a non-finite score")
        seen.add(index)
        parsed.append((index, score))
    return parsed


class CrossEncoderReranker:
    """Use ``BAAI/bge-reranker-v2-m3`` through Sentence Transformers.

    The model is loaded lazily by the constructor. Install the optional
    ``rerank-local`` extra before creating this class in a worker process.
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
                "sentence-transformers; install multimodal-rag-assistant[rerank-local]"
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
