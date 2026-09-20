"""Structured citation generation, validation, and streaming redaction."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence

from .models import Chunk, Citation

CITATION_START = "<<CITATIONS>>"
CITATION_END = "<<END_CITATIONS>>"
_CITATION_BLOCK_RE = re.compile(
    re.escape(CITATION_START) + r"\s*(?P<body>.*?)\s*" + re.escape(CITATION_END),
    re.DOTALL,
)
_JSON_FENCE_RE = re.compile(r"```json\s*(?P<body>\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


def format_timestamp(seconds: float | None) -> str:
    if seconds is None:
        return ""
    total = max(0, int(round(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def citation_label(chunk: Chunk) -> str:
    """Create a stable human-readable label from trusted chunk metadata."""

    if chunk.source_type in {"audio", "video"} and chunk.time_start is not None:
        end = format_timestamp(chunk.time_end)
        return f"{chunk.file_id} {format_timestamp(chunk.time_start)}-{end}"
    if chunk.source_type == "document" and chunk.page is not None:
        return f"{chunk.file_id} p.{chunk.page}"
    if chunk.source_type == "image":
        return f"{chunk.file_id} image"
    return chunk.file_id


def citation_from_chunk(chunk: Chunk) -> Citation:
    return Citation(
        chunk_id=chunk.chunk_id,
        file_id=chunk.file_id,
        source_type=chunk.source_type,
        label=citation_label(chunk),
        page=chunk.page,
        time_start=chunk.time_start,
        time_end=chunk.time_end,
        media_path=chunk.media_path,
    )


class CitationParser:
    """Parse and validate model citations against retrieved evidence only."""

    def parse(
        self,
        raw_text: str,
        chunks: Iterable[Chunk] | Mapping[str, Chunk],
    ) -> tuple[str, list[Citation]]:
        chunk_map = (
            dict(chunks)
            if isinstance(chunks, Mapping)
            else {chunk.chunk_id: chunk for chunk in chunks}
        )
        payload = self._find_payload(raw_text)
        requested_ids: list[str] = []
        if payload:
            raw_citations = payload.get("citations", [])
            if isinstance(raw_citations, list):
                for item in raw_citations:
                    if isinstance(item, str):
                        requested_ids.append(item)
                    elif isinstance(item, Mapping) and item.get("chunk_id"):
                        requested_ids.append(str(item["chunk_id"]))
        if not requested_ids:
            requested_ids = [
                chunk_id
                for chunk_id in chunk_map
                if f"[{chunk_id}]" in raw_text
            ]
        citations: list[Citation] = []
        seen: set[str] = set()
        for chunk_id in requested_ids:
            if chunk_id in seen or chunk_id not in chunk_map:
                continue
            seen.add(chunk_id)
            citations.append(citation_from_chunk(chunk_map[chunk_id]))
        clean_text = _CITATION_BLOCK_RE.sub("", raw_text).strip()
        clean_text = _JSON_FENCE_RE.sub("", clean_text).strip()
        return clean_text, citations

    @staticmethod
    def _find_payload(raw_text: str) -> dict[str, object] | None:
        matches = list(_CITATION_BLOCK_RE.finditer(raw_text))
        bodies = [match.group("body") for match in matches]
        bodies.extend(match.group("body") for match in _JSON_FENCE_RE.finditer(raw_text))
        for body in bodies:
            try:
                decoded = json.loads(body)
            except json.JSONDecodeError:
                continue
            if isinstance(decoded, dict):
                return decoded
        return None

    @staticmethod
    def to_block(citations: Sequence[Citation]) -> str:
        payload = {"citations": [citation.to_dict() for citation in citations]}
        return f"{CITATION_START}\n{json.dumps(payload, ensure_ascii=False)}\n{CITATION_END}"


class StreamingCitationSplitter:
    """Hide the machine-readable citation block while text streams to clients."""

    def __init__(self) -> None:
        self._pending = ""
        self._in_citations = False

    def feed(self, delta: str) -> str:
        if self._in_citations:
            return ""
        self._pending += delta
        marker_index = self._pending.find(CITATION_START)
        if marker_index >= 0:
            visible = self._pending[:marker_index]
            self._pending = ""
            self._in_citations = True
            return visible
        holdback = len(CITATION_START) - 1
        if len(self._pending) <= holdback:
            return ""
        visible = self._pending[:-holdback]
        self._pending = self._pending[-holdback:]
        return visible

    def finish(self) -> str:
        if self._in_citations:
            return ""
        visible = self._pending
        self._pending = ""
        return visible
