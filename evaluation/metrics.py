"""Deterministic retrieval and citation metrics for regression evaluation."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CaseMetrics:
    case_id: str
    precision_at_k: float
    recall_at_k: float
    hit_rate: float
    mrr: float
    citation_accuracy: float | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "precision_at_k": self.precision_at_k,
            "recall_at_k": self.recall_at_k,
            "hit_rate": self.hit_rate,
            "mrr": self.mrr,
            "citation_accuracy": self.citation_accuracy,
        }


def precision_at_k(retrieved: Sequence[str], relevant: Iterable[str], k: int) -> float:
    if k <= 0:
        return 0.0
    relevant_set = set(relevant)
    selected = list(retrieved[:k])
    return sum(item in relevant_set for item in selected) / len(selected) if selected else 0.0


def recall_at_k(retrieved: Sequence[str], relevant: Iterable[str], k: int) -> float:
    relevant_set = set(relevant)
    if not relevant_set or k <= 0:
        return 0.0
    return len(set(retrieved[:k]) & relevant_set) / len(relevant_set)


def hit_rate(retrieved: Sequence[str], relevant: Iterable[str], k: int) -> float:
    relevant_set = set(relevant)
    return float(bool(set(retrieved[:k]) & relevant_set)) if relevant_set and k > 0 else 0.0


def mean_reciprocal_rank(retrieved: Sequence[str], relevant: Iterable[str], k: int) -> float:
    relevant_set = set(relevant)
    for rank, item in enumerate(retrieved[:k], start=1):
        if item in relevant_set:
            return 1.0 / rank
    return 0.0


def citation_accuracy(cited: Iterable[str], relevant: Iterable[str]) -> float:
    cited_set = set(cited)
    if not cited_set:
        return 0.0
    return len(cited_set & set(relevant)) / len(cited_set)


def evaluate_case(row: Mapping[str, object], *, k: int = 5) -> CaseMetrics:
    retrieved = [str(item) for item in row.get("retrieved_chunk_ids", [])]
    relevant = [str(item) for item in row.get("expected_chunk_ids", [])]
    cited_raw = row.get("cited_chunk_ids")
    cited = None if cited_raw is None else [str(item) for item in cited_raw]
    return CaseMetrics(
        case_id=str(row.get("case_id", "unknown")),
        precision_at_k=precision_at_k(retrieved, relevant, k),
        recall_at_k=recall_at_k(retrieved, relevant, k),
        hit_rate=hit_rate(retrieved, relevant, k),
        mrr=mean_reciprocal_rank(retrieved, relevant, k),
        citation_accuracy=None if cited is None else citation_accuracy(cited, relevant),
    )


def aggregate(metrics: Sequence[CaseMetrics]) -> dict[str, float | int | None]:
    if not metrics:
        return {
            "cases": 0,
            "precision_at_k": 0.0,
            "recall_at_k": 0.0,
            "hit_rate": 0.0,
            "mrr": 0.0,
            "citation_accuracy": None,
        }
    citation_values = [item.citation_accuracy for item in metrics if item.citation_accuracy is not None]
    return {
        "cases": len(metrics),
        "precision_at_k": _mean(item.precision_at_k for item in metrics),
        "recall_at_k": _mean(item.recall_at_k for item in metrics),
        "hit_rate": _mean(item.hit_rate for item in metrics),
        "mrr": _mean(item.mrr for item in metrics),
        "citation_accuracy": None if not citation_values else _mean(citation_values),
    }


def _mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0
