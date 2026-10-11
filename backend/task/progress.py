"""One task projection and elapsed-time accounting for API and file metadata."""

from copy import deepcopy
from datetime import datetime

STAGES = ("PARSING", "SLICING", "EMBEDDING", "INDEXING")
PUBLIC_FIELDS = (
    "file_id", "task_type", "generation", "status", "sub_status", "progress",
    "error_msg", "retry_count", "created_at", "updated_at", "started_at", "completed_at",
    "failed_stage", "stage_metrics", "indexing_report",
)


def task_view(task):
    return {"task_id": task.id, **{name: getattr(task, name) for name in PUBLIC_FIELDS}}


def file_task_metadata(task):
    return {
        "task_id": task.id, "task_status": task.status, "task_stage": task.sub_status,
        "task_progress": task.progress, "error": task.error_msg,
        "failed_stage": task.failed_stage, "retry_count": task.retry_count,
        "stage_metrics": task.stage_metrics, "indexing_report": task.indexing_report,
        "task_started_at": task.started_at.isoformat() + "Z" if task.started_at else None,
        "task_completed_at": task.completed_at.isoformat() + "Z" if task.completed_at else None,
    }


def update_metrics(task, stage, status, now, *, completed=None, total=None):
    metrics = deepcopy(task.stage_metrics or {})
    timestamp = now.isoformat() + "Z"
    for name, item in metrics.items():
        active = item.get("active_since")
        if active and (name != stage or status != "PROCESSING"):
            started = datetime.fromisoformat(active.removesuffix("Z"))
            item["elapsed_ms"] = item.get("elapsed_ms", 0) + max(0, int((now - started).total_seconds() * 1000))
            item["active_since"] = None
            item["completed_at"] = timestamp
            item["status"] = "SUCCESS" if status == "SUCCESS" or stage in STAGES else status
    if stage in STAGES:
        item = metrics.setdefault(stage, {
            "started_at": timestamp, "completed_at": None, "elapsed_ms": 0,
            "active_since": None, "completed": None, "total": None,
        })
        item["status"] = status
        if status == "PROCESSING" and item.get("active_since") is None:
            item["active_since"] = timestamp
            item["completed_at"] = None
        if completed is not None:
            item["completed"] = completed
        if total is not None:
            item["total"] = total
    if status == "PENDING" and task.failed_stage in metrics:
        metrics[task.failed_stage]["status"] = "RETRYING"
    task.stage_metrics = metrics or None
