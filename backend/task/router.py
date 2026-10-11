"""Owned task progress HTTP endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import get_current_user
from backend.auth.models import User
from backend.infrastructure.database.session import get_session
from backend.task.schemas import TaskOut
from backend.task.service import TaskService

router = APIRouter(tags=["document pipeline"])


@router.get("/tasks/{id}", response_model=TaskOut)
async def task_status(
    id: str,
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_session)],
):
    return await TaskService(db).task_status(id, current.id)
