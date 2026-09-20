"""Lexical, vector, and rank-fusion retrieval primitives."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import replace
from typing import Any, Mapping, Protocol, Sequence

from .models import Chunk, RetrievalCandidate

TOKEN_RE = re.compile(r"[\u4e00-\u9fff]|[A-Za-z0-9_]+")


class Retriever(Protocol):
    def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        filters: Mapping[str, Any] | None = None,
    ) -> list[RetrievalCandidate]: ...


def tokenize(text: str) -> list[str]:
    """Tokenize mixed Chinese/English text without requiring a native analyzer."""

    return [token.lower() for token in TOKEN_RE.findall(text)]


def _matches_filters(chunk: Chunk, filters: Mapping[str, Any] | None) -> bool:
    if not filters:
        return True
    for key, expected in filters.items():
        actual = getattr(chunk, key, None)
        if actual is None:
            actual = chunk.extra.get(key)
        if isinstance(expected, (set, tuple, list, frozenset)):
            if actual not in expected:
                return False
        elif actual != expected:
            return False
    return True


class BM25Retriever:
    """Small, dependency-free BM25Okapi retriever for lexical recall.

    It is intended for a service-local index or a testable baseline. At larger
    scale the same interface can be backed by Elasticsearch, OpenSearch, or a
    Qdrant sparse-vector index without changing the fusion layer.
    """

    def __init__(self, chunks: Sequence[Chunk], *, k1: float = 1.5, b: float = 0.75) -> None:
        if k1 <= 0:
            raise ValueError("k1 must be positive")
        if not 0 <= b <= 1:
            raise ValueError("b must be between 0 and 1")
        self.chunks = tuple(chunks)
        self.k1 = k1
        self.b = b
        self._tokens = [tokenize(chunk.content) for chunk in self.chunks]
        self._term_frequencies = [Counter(tokens) for tokens in self._tokens]
        self._document_frequency: Counter[str] = Counter()
        for tokens in self._tokens:
            self._document_frequency.update(set(tokens))
        self._avgdl = sum(len(tokens) for tokens in self._tokens) / max(len(self._tokens), 1)

    def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        filters: Mapping[str, Any] | None = None,
    ) -> list[RetrievalCandidate]:
        if top_k <= 0:
            return []
        query_terms = tokenize(query)
        if not query_terms:
            return []
        query_term_set = set(query_terms)
        document_count = len(self.chunks)
        scored: list[tuple[float, int]] = []
        for index, chunk in enumerate(self.chunks):
            if not _matches_filters(chunk, filters):
                continue
            term_frequencies = self._term_frequencies[index]
            document_length = len(self._tokens[index])
            score = 0.0
            for term in query_term_set:
                frequency = term_frequencies.get(term, 0)
                if not frequency:
                    continue
                df = self._document_frequency[term]
                idf = math.log(1 + (document_count - df + 0.5) / (df + 0.5))
                denominator = frequency + self.k1 * (
                    1 - self.b + self.b * document_length / max(self._avgdl, 1e-9)
                )
                score += idf * frequency * (self.k1 + 1) / denominator
            if score > 0:
                scored.append((score, index))
        scored.sort(key=lambda item: (-item[0], self.chunks[item[1]].chunk_id))
        return [
            RetrievalCandidate(
                chunk=self.chunks[index],
                score=score,
                raw_score=score,
                source="bm25",
                rank=rank,
            )
            for rank, (score, index) in enumerate(scored[:top_k], start=1)
        ]


def reciprocal_rank_fusion(
    result_sets: Mapping[str, Sequence[RetrievalCandidate]],
    *,
    top_k: int = 10,
    rank_constant: float = 60.0,
    weights: Mapping[str, float] | None = None,
) -> list[RetrievalCandidate]:
    """Fuse ranked result lists with weighted Reciprocal Rank Fusion.

    ``rank_constant=60`` is the conventional RRF setting; it is configurable
    because Qdrant's native fusion defaults differ and should be tuned per corpus.
    """

    if rank_constant <= 0:
        raise ValueError("rank_constant must be positive")
    if top_k <= 0:
        return []
    fused: dict[str, dict[str, Any]] = {}
    for name, candidates in result_sets.items():
        weight = 1.0 if weights is None else float(weights.get(name, 1.0))
        if weight < 0:
            raise ValueError("RRF weights must be non-negative")
        for zero_based_rank, candidate in enumerate(candidates):
            rank = zero_based_rank + 1
            item = fused.setdefault(
                candidate.chunk_id,
                {"candidate": candidate, "score": 0.0, "sources": set(), "raw_score": None},
            )
            item["score"] += weight / (rank_constant + rank)
            # The result-set key is authoritative: a candidate object may carry
            # the source of the retriever that originally created it, but the
            # same object can legitimately be reused in another ranked list.
            item["sources"].add(name)
            raw_score = candidate.raw_score if candidate.raw_score is not None else candidate.score
            if item["raw_score"] is None or raw_score > item["raw_score"]:
                item["raw_score"] = raw_score
    ranked = sorted(
        fused.values(),
        key=lambda item: (-item["score"], item["candidate"].chunk_id),
    )[:top_k]
    return [
        replace(
            item["candidate"],
            score=item["score"],
            fused_score=item["score"],
            raw_score=item["raw_score"],
            source="+".join(sorted(item["sources"])),
            rank=rank,
        )
        for rank, item in enumerate(ranked, start=1)
    ]


class HybridRetriever:
    """Combine a dense/vector retriever and BM25 with weighted RRF."""

    def __init__(
        self,
        bm25: BM25Retriever,
        vector: Retriever | None = None,
        *,
        candidate_k: int = 50,
        dense_weight: float = 1.0,
        lexical_weight: float = 1.0,
        rank_constant: float = 60.0,
    ) -> None:
        if candidate_k <= 0:
            raise ValueError("candidate_k must be positive")
        self.bm25 = bm25
        self.vector = vector
        self.candidate_k = candidate_k
        self.weights = {"dense": dense_weight, "bm25": lexical_weight}
        self.rank_constant = rank_constant

    def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        filters: Mapping[str, Any] | None = None,
    ) -> list[RetrievalCandidate]:
        result_sets: dict[str, Sequence[RetrievalCandidate]] = {
            "bm25": self.bm25.search(query, top_k=self.candidate_k, filters=filters)
        }
        if self.vector is not None:
            dense_results = self.vector.search(query, top_k=self.candidate_k, filters=filters)
            result_sets["dense"] = [replace(item, source=item.source or "dense") for item in dense_results]
        return reciprocal_rank_fusion(
            result_sets,
            top_k=top_k,
            rank_constant=self.rank_constant,
            weights=self.weights,
        )


class StaticVectorRetriever:
    """Deterministic vector-retriever double useful for tests and local demos."""

    def __init__(self, results: Mapping[str, Sequence[RetrievalCandidate]]) -> None:
        self.results = dict(results)

    def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        filters: Mapping[str, Any] | None = None,
    ) -> list[RetrievalCandidate]:
        candidates = self.results.get(query, ())
        filtered = [item for item in candidates if _matches_filters(item.chunk, filters)]
        return [replace(item, rank=rank) for rank, item in enumerate(filtered[:top_k], start=1)]
