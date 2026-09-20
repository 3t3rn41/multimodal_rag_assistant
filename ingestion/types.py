"""Input records produced by document, ASR, and video-frame extractors."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class DocumentBlock:
    """A semantic document block before it is converted to a ``Chunk``."""

    text: str
    page: int | None = None
    heading: str | None = None
    media_path: str | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("document block text must not be empty")
        if self.page is not None and self.page <= 0:
            raise ValueError("document page must be positive")


@dataclass(frozen=True, slots=True)
class TranscriptSegment:
    """A timestamped ASR segment used as the media alignment backbone."""

    start: float
    end: float
    text: str

    def __post_init__(self) -> None:
        if self.start < 0:
            raise ValueError("transcript start must not be negative")
        if self.end <= self.start:
            raise ValueError("transcript end must be greater than start")
        if not self.text.strip():
            raise ValueError("transcript text must not be empty")


@dataclass(frozen=True, slots=True)
class FrameDescription:
    """A timestamped visual description generated from an extracted frame."""

    timestamp: float
    description: str
    media_path: str

    def __post_init__(self) -> None:
        if self.timestamp < 0:
            raise ValueError("frame timestamp must not be negative")
        if not self.description.strip():
            raise ValueError("frame description must not be empty")
        if not self.media_path.strip():
            raise ValueError("frame media_path must not be empty")
