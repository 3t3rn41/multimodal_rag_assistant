"""Documentation of existing SSE data; these models do not rewrite the stream."""

from typing import Literal

from pydantic import BaseModel


class StartEvent(BaseModel):
    event: Literal["start"]
    session_id: str


class AnswerChunkEvent(BaseModel):
    event: Literal["answer_chunk"]
    session_id: str
    chunk: str


class CitationEvent(BaseModel):
    event: Literal["citation"]
    session_id: str
    chunk_id: str
    file_id: str
    source_type: str
    page: int | None
    time_start: float | None
    time_end: float | None
    media_path: str | None
    label: str
    doc_id: int | None
    doc_title: str
    preview: str


class StageEvent(BaseModel):
    event: Literal["stage"]
    session_id: str
    type: Literal["stage"]
    stage: Literal["retrieval", "rerank", "generation", "citations"]
    status: Literal["running", "done"]
    label: str
    count: int | None = None
    duration_ms: int | None = None


class DoneEvent(BaseModel):
    event: Literal["done"]
    session_id: str
    answer: str
    citations: list[dict]
    message_id: int
    iterations: int
    duration_ms: int
    usage: dict | None
    cost: float | None


class AbortedEvent(BaseModel):
    event: Literal["aborted"]
    session_id: str
    message: str


class StreamErrorEvent(BaseModel):
    event: Literal["error"]
    session_id: str
    message: str


SSE_MODELS = (
    StartEvent,
    AnswerChunkEvent,
    CitationEvent,
    StageEvent,
    DoneEvent,
    AbortedEvent,
    StreamErrorEvent,
)
