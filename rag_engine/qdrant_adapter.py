"""Optional Qdrant adapter using the current ``query_points`` API."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from .models import Chunk, RetrievalCandidate


class QdrantVectorRetriever:
    """Adapt a Qdrant collection to the local retriever protocol.

    ``qdrant-client`` is imported lazily so the dependency-free BM25 and fusion
    components remain usable in unit tests and worker startup checks.
    """

    def __init__(
        self,
        client: Any,
        collection_name: str,
        embed_query: Callable[[str], list[float]],
        *,
        vector_name: str | None = None,
    ) -> None:
        self.client = client
        self.collection_name = collection_name
        self.embed_query = embed_query
        self.vector_name = vector_name

    def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        filters: Any | None = None,
    ) -> list[RetrievalCandidate]:
        kwargs: dict[str, Any] = {
            "collection_name": self.collection_name,
            "query": self.embed_query(query),
            "query_filter": filters,
            "limit": top_k,
            "with_payload": True,
        }
        if self.vector_name:
            kwargs["using"] = self.vector_name
        response = self.client.query_points(**kwargs)
        points = getattr(response, "points", response)
        results: list[RetrievalCandidate] = []
        for rank, point in enumerate(points, start=1):
            payload = dict(getattr(point, "payload", None) or {})
            point_id = str(getattr(point, "id", ""))
            chunk = Chunk.from_payload(payload, fallback_id=point_id)
            score = float(getattr(point, "score", 0.0))
            results.append(
                RetrievalCandidate(
                    chunk=chunk,
                    score=score,
                    raw_score=score,
                    source="dense",
                    rank=rank,
                )
            )
        return results
