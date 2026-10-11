"""Authenticated cleanup history and retry endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import get_current_user
from backend.auth.models import User
from backend.cleanup.schemas import CleanupJobOut, CleanupPage, CleanupStatus
from backend.cleanup.service import CleanupService
from backend.infrastructure.database.session import get_session

router = APIRouter(prefix="/cleanup-jobs", tags=["resource cleanup"])
Current = Annotated[User, Depends(get_current_user)]
DB = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=CleanupPage)
async def list_jobs(current: Current, db: DB, status: CleanupStatus | None = None,
                    cursor: Annotated[str | None, Query(max_length=36)] = None,
                    limit: Annotated[int, Query(ge=1, le=100)] = 20):
    return await CleanupService(db).page(current.id, status=status, cursor=cursor, limit=limit)


@router.post("/{job_id}/retry", response_model=CleanupJobOut)
async def retry_job(job_id: str, current: Current, db: DB):
    return await CleanupService(db).retry(job_id, current.id)
