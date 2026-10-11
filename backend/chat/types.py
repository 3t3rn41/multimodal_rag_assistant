"""State shared by chat orchestration and streaming."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from backend.chat.models import SessionStatus


@dataclass
class StreamState:
    answer: str = ""
    citations: list[dict] = field(default_factory=list)
    status: SessionStatus = SessionStatus.ERROR
    error: str | None = None
    retrieved: list = field(default_factory=list)
    model_profile: dict = field(default_factory=dict)
    steps: list[dict] = field(default_factory=list)
    started: float = field(default_factory=time.monotonic)
