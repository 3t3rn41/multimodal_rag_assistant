"""SSE framing, cancellation and trusted references; persistence is injected."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Sequence
from typing import Any

import anyio

from backend.chat.configuration import ChatConfiguration
from backend.chat.errors import ChatServiceError
from backend.chat.models import SessionStatus
from backend.chat.rag import pipeline_events
from backend.chat.types import StreamState
from rag_engine.citations import citation_from_chunk
from rag_engine.models import Chunk

logger = logging.getLogger(__name__)


def frontend_citations(
    items: Sequence[dict], chunks: Sequence[Chunk]
) -> list[dict[str, Any]]:
    """Never expose model-provided paths/pages or out-of-scope references."""
    trusted = {chunk.chunk_id: chunk for chunk in chunks}
    result = []
    seen = set()
    for item in items:
        chunk_id = str(item.get("chunk_id", ""))
        chunk = trusted.get(chunk_id)
        if chunk is None or chunk_id in seen:
            continue
        seen.add(chunk_id)
        citation = citation_from_chunk(chunk).to_dict()
        citation.update(
            {
                "doc_id": chunk.extra.get("doc_id"),
                "doc_title": chunk.extra.get("file_name", chunk.file_id),
                "preview": chunk.content[:500],
            }
        )
        result.append(citation)
    return result


def normalize_answer(answer: str, citations: Sequence[dict]) -> str:
    for item in citations:
        chunk_id = item["chunk_id"]
        answer = answer.replace(f"[{chunk_id}]", f"[chunk:{chunk_id}]")
    return answer


def sse_frame(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps({'event': event, **payload}, ensure_ascii=False)}\n\n"


async def cancellable_events(source: AsyncIterator[dict], abort: asyncio.Event):
    """Race every awaited model/retrieval event against explicit user abort."""
    iterator = source.__aiter__()
    aborted = asyncio.create_task(abort.wait())
    pending = None
    try:
        while not abort.is_set():
            pending = asyncio.create_task(anext(iterator))
            done, _ = await asyncio.wait(
                {pending, aborted}, return_when=asyncio.FIRST_COMPLETED
            )
            if aborted in done:
                break
            try:
                yield pending.result()
            except StopAsyncIteration:
                return
            pending = None
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        aborted.cancel()
        await asyncio.gather(aborted, return_exceptions=True)
        await iterator.aclose()


async def stream_turn(
    session_id: int,
    chunks: Sequence[Chunk],
    config: ChatConfiguration,
    question: str,
    history: Sequence[dict[str, str]],
    abort: asyncio.Event,
    *,
    event_source=pipeline_events,
    persist,
) -> AsyncIterator[str]:
    state = StreamState(
        model_profile={
            "embedding_model": config.embedding.model,
            "vector_collection": config.collection,
            "rerank_enabled": config.reranker is not None,
            "rerank_model": config.reranker.model if config.reranker else None,
            "llm_model": config.llm.model,
        }
    )
    saved = False
    events = None
    sid = f"sess_{session_id}"
    try:
        yield sse_frame("start", {"session_id": sid})
        source = event_source(chunks, config, question, history)
        events = cancellable_events(source, abort)
        async for event in events:
            kind = event.get("type")
            if kind == "text":
                delta = str(event.get("delta", ""))
                state.answer += delta
                yield sse_frame("answer_chunk", {"session_id": sid, "chunk": delta})
            elif kind == "citations":
                state.citations = frontend_citations(event.get("items", []), chunks)
                for citation in state.citations:
                    yield sse_frame("citation", {"session_id": sid, **citation})
            elif kind == "done":
                state.citations = frontend_citations(event.get("citations", []), chunks)
                state.answer = normalize_answer(
                    str(event.get("answer", state.answer)), state.citations
                )
                state.retrieved = event.get("retrieved", [])
                state.status = SessionStatus.DONE
                message_id = await persist(session_id, state)
                saved = True
                yield sse_frame(
                    "done",
                    {
                        "session_id": sid,
                        "answer": state.answer,
                        "citations": state.citations,
                        "message_id": message_id,
                        "iterations": 1,
                        "duration_ms": int((time.monotonic() - state.started) * 1000),
                        "usage": None,
                        "cost": None,
                    },
                )
                return
            elif kind == "stage":
                step = {
                    key: event[key]
                    for key in ("stage", "status", "label", "count", "duration_ms")
                    if key in event
                }
                step["type"] = "stage"
                existing = next(
                    (
                        i
                        for i, item in enumerate(state.steps)
                        if item.get("stage") == step["stage"]
                    ),
                    None,
                )
                if existing is None:
                    state.steps.append(step)
                else:
                    state.steps[existing] = {**state.steps[existing], **step}
                yield sse_frame("stage", {"session_id": sid, **step})
        if abort.is_set():
            state.status = SessionStatus.ABORTED
            state.error = "user_aborted"
            await persist(session_id, state)
            saved = True
            yield sse_frame(
                "aborted",
                {"session_id": sid, "message": "已中断，已生成内容和会话已保存。"},
            )
        else:
            raise ChatServiceError("问答服务提前结束，请重试。")
    except (asyncio.CancelledError, GeneratorExit):
        state.status = SessionStatus.ABORTED
        state.error = "client_disconnected"
        raise
    except Exception:  # noqa: BLE001 - redact all third-party transport errors
        # External exception strings can contain request URLs, headers or keys.
        logger.warning("Stage-2 chat failed for session %s", session_id)
        state.status = SessionStatus.ERROR
        state.error = (
            "问答服务调用失败，请检查向量服务、模型接口、密钥有效性和网络连接，再重试。"
        )
        if not saved:
            await persist(session_id, state)
            saved = True
        yield sse_frame("error", {"session_id": sid, "message": state.error})
    finally:
        # A return on the done event must also close the provider iterator.
        # Starlette cancels disconnected streams in an AnyIO cancellation scope.
        with anyio.CancelScope(shield=True):
            try:
                if events is not None:
                    await events.aclose()
            finally:
                if not saved:
                    await persist(session_id, state)
