"""Turn extracted document and media records into C-compatible ``Chunk`` objects."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from uuid import uuid4

from rag_engine.models import Chunk

from .types import DocumentBlock, FrameDescription, TranscriptSegment


def chunk_document(
    file_id: str,
    blocks: Iterable[DocumentBlock],
    *,
    max_chars: int = 1_200,
    overlap_chars: int = 160,
) -> list[Chunk]:
    """Split semantic document blocks while preserving page and heading metadata.

    The current implementation uses deterministic character windows. Extractors
    remain responsible for producing semantic blocks, so headings and page
    boundaries are not lost before this fallback splitter runs.
    """

    _validate_file_id(file_id)
    _validate_window(max_chars, overlap_chars)

    chunks: list[Chunk] = []
    for block in blocks:
        pieces = _split_text(block.text.strip(), max_chars, overlap_chars)
        for piece_index, piece in enumerate(pieces):
            content = piece
            if block.heading and piece_index == 0:
                content = f"{block.heading.strip()}\n{piece}"
            extra = dict(block.extra)
            if block.heading:
                extra.setdefault("heading", block.heading.strip())
            extra.setdefault("qdrant_point_id", str(uuid4()))
            chunks.append(
                Chunk(
                    chunk_id=f"{file_id}:document:{len(chunks):04d}",
                    file_id=file_id,
                    source_type="document",
                    content=content,
                    page=block.page,
                    media_path=block.media_path,
                    extra=extra,
                )
            )
    return chunks


def image_chunk(
    file_id: str,
    *,
    description: str,
    media_path: str,
    extra: dict[str, object] | None = None,
) -> Chunk:
    """Create the single searchable chunk associated with one image."""

    _validate_file_id(file_id)
    if not description.strip():
        raise ValueError("image description must not be empty")
    if not media_path.strip():
        raise ValueError("image media_path must not be empty")
    metadata = dict(extra or {})
    metadata.setdefault("modality", "image")
    metadata.setdefault("qdrant_point_id", str(uuid4()))
    return Chunk(
        chunk_id=f"{file_id}:image",
        file_id=file_id,
        source_type="image",
        content=description.strip(),
        media_path=media_path,
        extra=metadata,
    )


def chunk_media(
    file_id: str,
    transcripts: Sequence[TranscriptSegment],
    frames: Sequence[FrameDescription],
    *,
    source_type: str = "video",
    window_seconds: float = 30.0,
    source_media_path: str | None = None,
) -> list[Chunk]:
    """Fuse ASR and frame descriptions into fixed, time-addressable windows.

    Each transcript segment is assigned exactly once, using its start timestamp
    as the owning window. This avoids duplicating a long ASR segment that crosses
    a boundary. Chunk time metadata records the actual evidence bounds while
    ``extra.window_start``/``window_end`` retain the fixed retrieval bucket.
    Empty windows are omitted, which keeps the vector index free of silent or
    blank media spans.
    """

    _validate_file_id(file_id)
    if source_type not in {"audio", "video"}:
        raise ValueError("media source_type must be 'audio' or 'video'")
    if window_seconds <= 0 or not math.isfinite(window_seconds):
        raise ValueError("window_seconds must be a finite positive number")

    max_end = max(
        (segment.end for segment in transcripts),
        default=0.0,
    )
    max_end = max(max_end, max((frame.timestamp for frame in frames), default=0.0))
    if not transcripts and not frames:
        return []

    window_count = max(1, math.ceil(max_end / window_seconds))
    chunks: list[Chunk] = []
    for window_index in range(window_count):
        start = window_index * window_seconds
        end = (window_index + 1) * window_seconds
        matching_transcripts = [
            segment
            for segment in transcripts
            if math.floor(segment.start / window_seconds) == window_index
        ]
        matching_frames = [
            frame
            for frame in frames
            if start <= frame.timestamp < end
            or (window_index == window_count - 1 and frame.timestamp == end)
        ]
        if not matching_transcripts and not matching_frames:
            continue

        speech_text = " ".join(segment.text.strip() for segment in matching_transcripts)
        frame_descriptions = [frame.description.strip() for frame in matching_frames]
        content_parts: list[str] = []
        if speech_text:
            content_parts.append(f"语音转写：{speech_text}")
        if frame_descriptions:
            content_parts.append(f"画面描述：{'；'.join(frame_descriptions)}")

        frame_paths = [frame.media_path for frame in matching_frames]
        evidence_starts = [segment.start for segment in matching_transcripts]
        evidence_starts.extend(frame.timestamp for frame in matching_frames)
        evidence_ends = [segment.end for segment in matching_transcripts]
        evidence_ends.extend(frame.timestamp for frame in matching_frames)
        extra = {
            "speech_text": speech_text,
            "frame_descriptions": frame_descriptions,
            "frame_paths": frame_paths,
            "window_start": start,
            "window_end": end,
            "window_seconds": window_seconds,
            "qdrant_point_id": str(uuid4()),
        }
        if source_media_path:
            extra["source_media_path"] = source_media_path
        chunks.append(
            Chunk(
                chunk_id=f"{file_id}:{source_type}:{start:g}-{end:g}",
                file_id=file_id,
                source_type=source_type,
                content="\n".join(content_parts),
                time_start=min(evidence_starts),
                time_end=max(evidence_ends),
                media_path=frame_paths[0] if frame_paths else source_media_path,
                extra=extra,
            )
        )
    return chunks


def _split_text(text: str, max_chars: int, overlap_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    step = max_chars - overlap_chars
    return [text[start : start + max_chars] for start in range(0, len(text), step)]


def _validate_file_id(file_id: str) -> None:
    if not file_id.strip():
        raise ValueError("file_id must not be empty")


def _validate_window(max_chars: int, overlap_chars: int) -> None:
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be in [0, max_chars)")
