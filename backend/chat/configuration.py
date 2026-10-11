"""Application configuration of the unchanged Member C constructors."""

from __future__ import annotations

import math
import os
from collections.abc import Mapping
from dataclasses import dataclass, field

from backend.core.errors import ServiceError
from backend.infrastructure.jina.configuration import (
    JinaConfigurationError,
    embedding_configuration,
    jina_profile,
    rerank_configuration,
)
from ingestion.api_embeddings import MultimodalEmbeddingAPIConfig
from rag_engine.llm import OpenAICompatibleConfig
from rag_engine.rerank import JinaRerankConfig


class RetrievalConfigurationError(ServiceError):
    def __init__(self, message: str):
        super().__init__(message, 503)


@dataclass(frozen=True)
class RetrievalConfiguration:
    retrieval_k: int = 50
    answer_k: int = 8
    rank_constant: float = 60.0
    dense_weight: float = 1.0
    lexical_weight: float = 1.0


def retrieval_configuration(
    env: Mapping[str, str] | None = None,
) -> RetrievalConfiguration:
    values = os.environ if env is None else env
    parsed = {}
    for name, default, convert in (
        ("RAG_RETRIEVAL_K", 50, int),
        ("RAG_ANSWER_K", 8, int),
        ("RAG_RRF_RANK_CONSTANT", 60.0, float),
        ("RAG_DENSE_WEIGHT", 1.0, float),
        ("RAG_LEXICAL_WEIGHT", 1.0, float),
    ):
        try:
            value = convert(values.get(name) or default)
            if (
                not math.isfinite(value)
                or value < 0
                or (
                    name in {"RAG_RETRIEVAL_K", "RAG_ANSWER_K", "RAG_RRF_RANK_CONSTANT"}
                    and value == 0
                )
            ):
                raise ValueError()
        except (TypeError, ValueError, OverflowError):
            raise RetrievalConfigurationError(
                f"{name} 配置无效，请检查 .env。"
            ) from None
        parsed[name] = value
    if parsed["RAG_ANSWER_K"] > parsed["RAG_RETRIEVAL_K"]:
        raise RetrievalConfigurationError("RAG_ANSWER_K 不得超过 RAG_RETRIEVAL_K。")
    if parsed["RAG_DENSE_WEIGHT"] == parsed["RAG_LEXICAL_WEIGHT"] == 0:
        raise RetrievalConfigurationError(
            "RAG_DENSE_WEIGHT 和 RAG_LEXICAL_WEIGHT 不能同时为零。"
        )
    return RetrievalConfiguration(
        retrieval_k=parsed["RAG_RETRIEVAL_K"],
        answer_k=parsed["RAG_ANSWER_K"],
        rank_constant=parsed["RAG_RRF_RANK_CONSTANT"],
        dense_weight=parsed["RAG_DENSE_WEIGHT"],
        lexical_weight=parsed["RAG_LEXICAL_WEIGHT"],
    )


@dataclass(frozen=True)
class ChatConfiguration:
    llm: OpenAICompatibleConfig
    embedding: MultimodalEmbeddingAPIConfig
    collection: str = "jina_v5_omni_small_1024"
    vector_name: str = "dense"
    reranker: JinaRerankConfig | None = None
    retrieval: RetrievalConfiguration = field(default_factory=RetrievalConfiguration)

    @classmethod
    def from_answer(cls, llm):
        try:
            profile = jina_profile()
            embedding = embedding_configuration()
            reranker = rerank_configuration()
        except JinaConfigurationError as exc:
            raise ServiceError(str(exc), 503) from None
        return cls(
            llm=llm,
            embedding=embedding,
            collection=profile["vector_collection"],
            vector_name=profile["vector_name"],
            reranker=reranker,
            retrieval=retrieval_configuration(),
        )

