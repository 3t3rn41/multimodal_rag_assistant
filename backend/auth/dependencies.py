"""Verified email sessions are required; write requests also require CSRF tokens."""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.models import User
from backend.auth.service import SESSION_COOKIE, AuthService, token_hash
from backend.core.errors import ServiceError
from backend.infrastructure.database.session import get_session


async def get_current_user(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    auth, user = await AuthService(session).authenticate(
        request.cookies.get(SESSION_COOKIE)
    )
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        csrf = request.headers.get("X-CSRF-Token", "")
        if (
            not csrf
            or len(csrf) > 128
            or not hmac.compare_digest(auth.csrf_hash, token_hash(csrf))
        ):
            raise ServiceError("安全校验失败，请刷新页面后重试。", 403)
    return user
