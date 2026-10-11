"""HTTP request and response models for the task domain."""

from __future__ import annotations

from datetime import datetime

from backend.core.schemas import APIModel


class TaskOut(APIModel):
    task_id: str
    file_id: int
    task_type: str
    generation: int
    status: str
    sub_status: str
    progress: float
    error_msg: str | None = None
    failed_stage: str | None = None
    stage_metrics: dict | None = None
    indexing_report: dict | None = None
    retry_count: int
    created_at: datetime
    updated_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
