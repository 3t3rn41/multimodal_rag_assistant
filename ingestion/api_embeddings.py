"""API-only multimodal embeddings for text, image, audio, and video chunks.

The production configuration targets SiliconFlow's Qwen3-VL-Embedding API.
Audio and video chunks are represented by transcript text and representative
video frames because the embedding endpoint currently accepts text and images,
not raw audio or video.
"""

from __future__ import annotations

import math
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from rag_engine.models import Chunk


class EmbeddingAPIError(RuntimeError):
    """Raised when the configured embedding API returns an invalid response."""


class JsonTransport(Protocol):
    """Small HTTP boundary that keeps API behavior deterministic in tests."""

    def post_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        payload: dict[str, object],
        timeout: float,
    ) -> Mapping[str, Any]: ...


class HttpxJsonTransport:
    """Production JSON transport loaded lazily from the optional API extra."""

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
                "API embeddings require the 'api' optional dependency"
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
            raise EmbeddingAPIError(f"embedding API request failed: {exc}") from exc
        if not isinstance(data, Mapping):
            raise EmbeddingAPIError("embedding API response must be a JSON object")
        return data


@dataclass(frozen=True, slots=True)
class MultimodalEmbeddingAPIConfig:
    """Configuration for SiliconFlow's OpenAI-shaped embedding endpoint."""

    url: str
    api_key: str
    model: str = "Qwen/Qwen3-VL-Embedding-8B"
    dimensions: int | None = None
    timeout_seconds: float = 60.0

    def __post_init__(self) -> None:
        if not self.url.strip():
            raise ValueError("embedding API URL must not be empty")
        if not self.api_key.strip():
            raise ValueError("embedding API key must not be empty")
        if not self.model.strip():
            raise ValueError("embedding model must not be empty")
        if self.dimensions is not None and self.dimensions <= 0:
            raise ValueError("embedding dimensions must be positive")
        if self.timeout_seconds <= 0 or not math.isfinite(self.timeout_seconds):
            raise ValueError("embedding timeout must be a finite positive number")

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
    ) -> "MultimodalEmbeddingAPIConfig":
        """Load API settings without reading or logging any secret value."""

        values = os.environ if env is None else env
        api_key = values.get("RAG_EMBEDDING_API_KEY", "").strip() or values.get(
            "SILICONFLOW_API_KEY", ""
        ).strip()
        if not api_key:
            raise ValueError(
                "RAG_EMBEDDING_API_KEY or SILICONFLOW_API_KEY is required"
            )
        try:
            raw_dimensions = values.get("RAG_EMBEDDING_DIMENSIONS", "").strip()
            dimensions = int(raw_dimensions) if raw_dimensions else None
            timeout = float(values.get("RAG_EMBEDDING_TIMEOUT_SECONDS", "60"))
        except ValueError as exc:
            raise ValueError(
                "RAG_EMBEDDING_DIMENSIONS and RAG_EMBEDDING_TIMEOUT_SECONDS "
                "must be numeric"
            ) from exc
        return cls(
            url=values.get(
                "RAG_EMBEDDING_API_URL",
                "https://api.siliconflow.cn/v1/embeddings",
            ),
            api_key=api_key,
            model=values.get(
                "RAG_EMBEDDING_MODEL",
                "Qwen/Qwen3-VL-Embedding-8B",
            ),
            dimensions=dimensions,
            timeout_seconds=timeout,
        )


class ApiMultimodalEmbedder:
    """Embed all modalities through one text/image API and vector space.

    Document and audio chunks contribute text. Image and video chunks contribute
    both their searchable text and a resolvable image reference. Multiple vectors
    for one chunk are averaged after L2 normalization and normalized again.
    """

    def __init__(
        self,
        config: MultimodalEmbeddingAPIConfig,
        *,
        transport: JsonTransport | None = None,
        media_url_resolver: Callable[[str], str | None] | None = None,
    ) -> None:
        self.config = config
        self.transport = transport or HttpxJsonTransport()
        self.media_url_resolver = media_url_resolver

    def embed(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        """Embed corpus text through the configured multimodal API."""

        inputs = [{"text": text} for text in texts]
        return self._request(inputs)

    def embed_query(self, text: str) -> list[float]:
        """Embed a retrieval query for member C's Qdrant adapter."""

        vectors = self._request([{"text": text}])
        return list(vectors[0])

    def embed_chunks(self, chunks: Sequence[Chunk]) -> list[tuple[float, ...]]:
        """Embed chunk text and representative media in one API request."""

        inputs: list[dict[str, str]] = []
        groups: list[list[int]] = []
        for chunk in chunks:
            indexes: list[int] = []
            if chunk.content.strip():
                indexes.append(len(inputs))
                inputs.append({"text": chunk.content})
            media_url = self._media_url(chunk)
            if media_url is not None:
                indexes.append(len(inputs))
                inputs.append({"image": media_url})
            if not indexes:
                raise ValueError(f"chunk {chunk.chunk_id!r} has no embeddable content")
            groups.append(indexes)

        vectors = self._request(inputs)
        return [_mean_unit_vector([vectors[index] for index in group]) for group in groups]

    def _media_url(self, chunk: Chunk) -> str | None:
        if chunk.source_type not in {"image", "video"} or not chunk.media_path:
            return None
        value = chunk.media_path
        if self.media_url_resolver is not None:
            value = self.media_url_resolver(value) or ""
        if value.startswith(("https://", "http://", "data:")):
            return value
        return None

    def _request(
        self,
        inputs: Sequence[dict[str, str]],
    ) -> list[tuple[float, ...]]:
        if not inputs:
            return []
        payload: dict[str, object] = {
            "model": self.config.model,
            "encoding_format": "float",
            "input": list(inputs),
        }
        if self.config.dimensions is not None:
            payload["dimensions"] = self.config.dimensions
        response = self.transport.post_json(
            self.config.url,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            payload=payload,
            timeout=self.config.timeout_seconds,
        )
        return _parse_embeddings(response, expected=len(inputs))


def _parse_embeddings(
    response: Mapping[str, Any],
    *,
    expected: int,
) -> list[tuple[float, ...]]:
    data = response.get("data")
    if not isinstance(data, list):
        raise EmbeddingAPIError("embedding API response is missing data")
    indexed: dict[int, tuple[float, ...]] = {}
    for fallback_index, row in enumerate(data):
        if not isinstance(row, Mapping):
            raise EmbeddingAPIError("embedding API data entries must be objects")
        index = int(row.get("index", fallback_index))
        embedding = row.get("embedding")
        if not isinstance(embedding, Sequence) or isinstance(embedding, (str, bytes)):
            raise EmbeddingAPIError("embedding API entry is missing a vector")
        try:
            vector = tuple(float(value) for value in embedding)
        except (TypeError, ValueError) as exc:
            raise EmbeddingAPIError("embedding API returned a non-numeric vector") from exc
        if not vector or not all(math.isfinite(value) for value in vector):
            raise EmbeddingAPIError("embedding API returned an invalid vector")
        indexed[index] = vector
    if set(indexed) != set(range(expected)):
        raise EmbeddingAPIError(
            f"embedding API returned {len(indexed)} vectors for {expected} inputs"
        )
    dimensions = {len(vector) for vector in indexed.values()}
    if len(dimensions) != 1:
        raise EmbeddingAPIError("embedding API returned inconsistent dimensions")
    return [indexed[index] for index in range(expected)]


def _mean_unit_vector(vectors: Sequence[Sequence[float]]) -> tuple[float, ...]:
    normalized = [_unit_vector(vector) for vector in vectors]
    dimension = len(normalized[0])
    if any(len(vector) != dimension for vector in normalized):
        raise EmbeddingAPIError("cannot combine vectors with different dimensions")
    mean = tuple(
        sum(vector[index] for vector in normalized) / len(normalized)
        for index in range(dimension)
    )
    return _unit_vector(mean)


def _unit_vector(vector: Sequence[float]) -> tuple[float, ...]:
    norm = math.sqrt(sum(float(value) ** 2 for value in vector))
    if norm == 0 or not math.isfinite(norm):
        raise EmbeddingAPIError("embedding vector cannot be normalized")
    return tuple(float(value) / norm for value in vector)
