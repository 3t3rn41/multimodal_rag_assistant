"""Application retrieval and reranking using unchanged Member C components."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import replace
from typing import Any

from backend.chat.configuration import ChatConfiguration
from backend.chat.errors import ChatServiceError
from backend.infrastructure.jina.embedding import build_embedder
from backend.infrastructure.qdrant import get_client
from rag_engine.llm import OpenAICompatibleChatModel
from rag_engine.models import Chunk, RetrievalCandidate
from rag_engine.pipeline import RAGPipeline
from rag_engine.qdrant_adapter import QdrantVectorRetriever
from rag_engine.rerank import JinaReranker
from rag_engine.retrieval import BM25Retriever, HybridRetriever


class ScopedVectorRetriever:
    """Enforce an immutable SQL whitelist before and after Qdrant search."""

    def __init__(self, vector: Any, chunks: Sequence[Chunk]):
        self.vector = vector
        self.chunks = {chunk.chunk_id: chunk for chunk in chunks}

    def search(
        self, query: str, *, top_k: int = 10, filters: Any = None
    ) -> list[RetrievalCandidate]:
        from qdrant_client.models import FieldCondition, Filter, MatchAny

        del filters  # Scope comes exclusively from the SQL access check.
        query_filter = Filter(
            must=[
                FieldCondition(
                    key="chunk_id",
                    match=MatchAny(any=list(self.chunks)),
                )
            ]
        )
        candidates = self.vector.search(query, top_k=top_k, filters=query_filter)
        return [
            replace(candidate, chunk=self.chunks[candidate.chunk_id])
            for candidate in candidates
            if candidate.chunk_id in self.chunks
        ]


class PreparedRetriever:
    """Feed already fetched/reranked evidence to the unchanged async pipeline."""

    def __init__(self, candidates: Sequence[RetrievalCandidate]):
        self.candidates = list(candidates)

    def search(
        self, query: str, *, top_k: int = 10, filters: Any = None
    ) -> list[RetrievalCandidate]:
        del query, filters
        return self.candidates[:top_k]


class ConversationModel:
    """Give the model bounded conversation context, after the evidence rules."""

    def __init__(self, model: Any, history: Sequence[dict[str, str]]):
        self.model = model
        self.history = list(history)

    async def stream(
        self, messages: Sequence[Mapping[str, Any]], *, temperature: float = 0.0
    ):
        # System instructions remain first and the fresh evidence/question last.
        combined = (
            [messages[0], *self.history, *messages[1:]] if messages else self.history
        )
        async for delta in self.model.stream(combined, temperature=temperature):
            yield delta


def build_pipeline(
    chunks: Sequence[Chunk],
    config: ChatConfiguration,
    history: Sequence[dict[str, str]],
):
    """Create real providers only after configuration and access validation."""

    if config.reranker is None:
        raise ChatServiceError("系统 Jina Rerank 未配置，请检查 .env 并重启后端。")
    client = get_client(timeout=30)
    embedder = build_embedder(config.embedding)
    vector = QdrantVectorRetriever(
        client,
        config.collection,
        embedder.embed_query,
        vector_name=config.vector_name,
    )
    hybrid = HybridRetriever(
        BM25Retriever(chunks),
        ScopedVectorRetriever(vector, chunks),
        candidate_k=config.retrieval.retrieval_k,
        dense_weight=config.retrieval.dense_weight,
        lexical_weight=config.retrieval.lexical_weight,
        rank_constant=config.retrieval.rank_constant,
    )
    reranker = JinaReranker(config.reranker)
    model = ConversationModel(OpenAICompatibleChatModel(config.llm), history)
    return RAGPipeline(
        hybrid,
        model,
        reranker=reranker,
        retrieval_k=config.retrieval.retrieval_k,
        answer_k=config.retrieval.answer_k,
    ), client


async def pipeline_events(
    chunks: Sequence[Chunk],
    config: ChatConfiguration,
    question: str,
    history: Sequence[dict[str, str]],
    *,
    factory=build_pipeline,
) -> AsyncIterator[dict[str, Any]]:
    """No synchronous provider request may block the HTTP event loop."""
    pipeline = None
    resource = None
    try:
        pipeline, resource = await asyncio.to_thread(factory, chunks, config, history)
        retrieval_start = time.monotonic()
        yield {
            "type": "stage",
            "stage": "retrieval",
            "status": "running",
            "label": "检索资料",
        }
        retrieved = await asyncio.to_thread(
            pipeline.retriever.search, question, top_k=pipeline.retrieval_k
        )
        yield {
            "type": "stage",
            "stage": "retrieval",
            "status": "done",
            "label": "检索资料",
            "count": len(retrieved),
            "duration_ms": int((time.monotonic() - retrieval_start) * 1000),
        }
        rerank_start = time.monotonic()
        yield {
            "type": "stage",
            "stage": "rerank",
            "status": "running",
            "label": "重排候选",
        }
        reranked = await asyncio.to_thread(
            pipeline.reranker.rerank, question, retrieved, top_k=pipeline.answer_k
        )
        yield {
            "type": "stage",
            "stage": "rerank",
            "status": "done",
            "label": "重排候选",
            "count": len(reranked),
            "duration_ms": int((time.monotonic() - rerank_start) * 1000),
        }
        if not reranked:
            # This is a real empty search result, not a generated or demo answer.
            yield {
                "type": "done",
                "answer": "资料库中未找到足够依据。",
                "citations": [],
                "retrieved": [],
                "reranked": [],
            }
            return
        prepared = RAGPipeline(
            PreparedRetriever(reranked),
            pipeline.model,
            retrieval_k=len(reranked),
            answer_k=len(reranked),
            max_context_chars=pipeline.max_context_chars,
        )
        generation_start = time.monotonic()
        yield {
            "type": "stage",
            "stage": "generation",
            "status": "running",
            "label": "生成回答",
        }
        async for event in prepared.stream_answer(question):
            if event.get("type") == "citations":
                yield {
                    "type": "stage",
                    "stage": "generation",
                    "status": "done",
                    "label": "生成回答",
                    "duration_ms": int((time.monotonic() - generation_start) * 1000),
                }
                yield {
                    "type": "stage",
                    "stage": "citations",
                    "status": "done",
                    "label": "校验引用",
                    "count": len(event.get("items", [])),
                }
            if event.get("type") == "done":
                event["retrieved"] = [candidate.to_dict() for candidate in retrieved]
            yield event
    finally:
        if resource is not None:
            await asyncio.to_thread(resource.close)
