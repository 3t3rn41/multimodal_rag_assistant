"""Public cleanup status, with no storage credentials or object locations."""

from datetime import datetime
from typing import Literal

from backend.core.schemas import APIModel

CleanupStatus = Literal["PENDING", "PROCESSING", "SUCCESS", "FAILED"]


class CleanupJobOut(APIModel):
    cleanup_job_id: str
    file_id: int
    file_name: str
    kind: str
    target_generation: int
    status: CleanupStatus
    raw_status: str
    vector_status: str
    retry_count: int
    error_msg: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
    completed_at: datetime | None = None
    next_attempt_at: datetime


class CleanupPage(APIModel):
    items: list[CleanupJobOut]
    next_cursor: str | None = None
