"""End-to-end orchestration for retrieval, reranking, generation, and citations."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any

from .citations import CitationParser, StreamingCitationSplitter
from .llm import ChatModel, collect_stream
from .models import Citation, RetrievalCandidate
from .prompts import build_messages
from .rerank import NoOpReranker, Reranker
from .retrieval import Retriever


@dataclass(frozen=True, slots=True)
class AnswerResult:
    query: str
    answer: str
    citations: tuple[Citation, ...]
    retrieved: tuple[RetrievalCandidate, ...]
    reranked: tuple[RetrievalCandidate, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "answer": self.answer,
            "citations": [citation.to_dict() for citation in self.citations],
            "retrieved": [candidate.to_dict() for candidate in self.retrieved],
            "reranked": [candidate.to_dict() for candidate in self.reranked],
        }


class RAGPipeline:
    """Coordinate member C's retrieval and generation components."""

    def __init__(
        self,
        retriever: Retriever,
        model: ChatModel,
        *,
        reranker: Reranker | None = None,
        retrieval_k: int = 50,
        answer_k: int = 8,
        max_context_chars: int = 12_000,
    ) -> None:
        self.retriever = retriever
        self.model = model
        self.reranker = reranker or NoOpReranker()
        self.retrieval_k = retrieval_k
        self.answer_k = answer_k
        self.max_context_chars = max_context_chars
        self.citation_parser = CitationParser()

    def retrieve(self, query: str, *, filters: Mapping[str, Any] | None = None) -> tuple[
        list[RetrievalCandidate], list[RetrievalCandidate]
    ]:
        retrieved = self.retriever.search(query, top_k=self.retrieval_k, filters=filters)
        reranked = self.reranker.rerank(query, retrieved, top_k=self.answer_k)
        return retrieved, reranked

    async def answer(
        self,
        query: str,
        *,
        filters: Mapping[str, Any] | None = None,
        temperature: float = 0.0,
    ) -> AnswerResult:
        retrieved, reranked = self.retrieve(query, filters=filters)
        messages = build_messages(query, reranked, max_context_chars=self.max_context_chars)
        raw_answer = await collect_stream(self.model, messages, temperature=temperature)
        answer, citations = self.citation_parser.parse(raw_answer, [item.chunk for item in reranked])
        return AnswerResult(
            query=query,
            answer=answer,
            citations=tuple(citations),
            retrieved=tuple(retrieved),
            reranked=tuple(reranked),
        )

    async def stream_answer(
        self,
        query: str,
        *,
        filters: Mapping[str, Any] | None = None,
        temperature: float = 0.0,
    ) -> AsyncIterator[dict[str, Any]]:
        retrieved, reranked = self.retrieve(query, filters=filters)
        yield {"type": "context", "items": [item.to_dict() for item in reranked]}
        messages = build_messages(query, reranked, max_context_chars=self.max_context_chars)
        raw_parts: list[str] = []
        splitter = StreamingCitationSplitter()
        async for delta in self.model.stream(messages, temperature=temperature):
            raw_parts.append(delta)
            visible = splitter.feed(delta)
            if visible:
                yield {"type": "text", "delta": visible}
        trailing = splitter.finish()
        if trailing:
            yield {"type": "text", "delta": trailing}
        answer, citations = self.citation_parser.parse(
            "".join(raw_parts), [item.chunk for item in reranked]
        )
        yield {"type": "citations", "items": [citation.to_dict() for citation in citations]}
        yield {
            "type": "done",
            "answer": answer,
            "citations": [citation.to_dict() for citation in citations],
            "retrieved": [item.to_dict() for item in retrieved],
            "reranked": [item.to_dict() for item in reranked],
        }
