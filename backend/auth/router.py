from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import get_current_user
from backend.auth.models import User
from backend.auth.rate_limits import check_limit
from backend.auth.schemas import (
    PasswordResetInput,
    Credentials,
    EmailInput,
    RegistrationCodeInput,
    RegistrationHandleInput,
    RegistrationInput,
)
from backend.auth.service import (
    CSRF_COOKIE,
    REGISTRATION_CODE_MINUTES,
    REGISTRATION_RESEND_SECONDS,
    SESSION_COOKIE,
    AuthService,
    public_user,
)
from backend.core.config import settings
from backend.infrastructure.database.session import get_session

router = APIRouter(prefix="/auth", tags=["auth"])
DB = Annotated[AsyncSession, Depends(get_session)]


async def limits(request, email, operation):
    ip = request.client.host if request.client else "unknown"
    await check_limit(
        f"{operation}:ip",
        ip,
        30 if operation == "login" else 20,
        900 if operation == "login" else 3600,
    )
    await check_limit(
        f"{operation}:email",
        email,
        10 if operation == "login" else 5,
        900 if operation == "login" else 3600,
    )


@router.post("/register", status_code=202)
async def register(body: RegistrationInput, request: Request, db: DB):
    await limits(request, body.email, "register")
    await check_limit(
        "registration-code:cooldown", body.email, 1, REGISTRATION_RESEND_SECONDS
    )
    registration_token = await AuthService(db).register(
        body.email, body.password.get_secret_value()
    )
    return {
        "message": "如该邮箱可以注册，我们已发送 6 位数字验证码，请查看收件箱和垃圾邮件箱。",
        "registration_token": registration_token,
        "expires_in": REGISTRATION_CODE_MINUTES * 60,
        "resend_after": REGISTRATION_RESEND_SECONDS,
    }


@router.post("/resend-verification", status_code=202)
async def resend(body: RegistrationHandleInput, request: Request, db: DB):
    await limits(request, body.email, "register")
    await check_limit(
        "registration-code:cooldown", body.email, 1, REGISTRATION_RESEND_SECONDS
    )
    await AuthService(db).resend_registration(
        body.email, body.registration_token.get_secret_value()
    )
    return {
        "message": "新的验证码已发送，请使用最新邮件中的 6 位数字。",
        "resend_after": REGISTRATION_RESEND_SECONDS,
    }


@router.post("/verify-registration")
async def verify_registration(body: RegistrationCodeInput, request: Request, db: DB):
    await check_limit(
        "consume:ip", request.client.host if request.client else "unknown", 30, 900
    )
    await AuthService(db).verify_registration(
        body.email,
        body.registration_token.get_secret_value(),
        body.code.get_secret_value(),
    )
    return {"message": "邮箱验证成功，注册已完成，现在可以登录。"}


@router.post("/forgot-password", status_code=202)
async def forgot(body: EmailInput, request: Request, db: DB):
    await limits(request, body.email, "reset-mail")
    await AuthService(db).request_password_reset(body.email)
    return {"message": "如该邮箱已注册并验证，我们已发送重设密码邮件。"}


@router.post("/reset-password")
async def reset(body: PasswordResetInput, request: Request, db: DB):
    await check_limit(
        "consume:ip", request.client.host if request.client else "unknown", 30, 900
    )
    await AuthService(db).reset_password(body.token, body.password.get_secret_value())
    return {"message": "密码已重设，其他设备上的登录已失效。请重新登录。"}


@router.post("/login")
async def login(body: Credentials, request: Request, response: Response, db: DB):
    await limits(request, body.email, "login")
    service = AuthService(db)
    user, token, csrf = await service.login(
        body.email, body.password.get_secret_value()
    )
    previous = request.cookies.get(SESSION_COOKIE)
    if previous:
        await service.logout(previous)
    cookie = {
        "secure": settings.env.auth_cookie_secure,
        "samesite": "lax",
        "path": "/",
        "max_age": settings.env.auth_session_days * 86400,
    }
    response.set_cookie(SESSION_COOKIE, token, httponly=True, **cookie)
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, **cookie)
    return public_user(user)


@router.get("/me")
async def me(current: Annotated[User, Depends(get_current_user)]):
    return public_user(current)


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: DB,
    current: Annotated[User, Depends(get_current_user)],
):
    if request.cookies.get(SESSION_COOKIE):
        await AuthService(db).logout(request.cookies[SESSION_COOKIE])
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        secure=settings.env.auth_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    response.delete_cookie(
        CSRF_COOKIE, path="/", secure=settings.env.auth_cookie_secure, samesite="lax"
    )
    return {"message": "已退出登录。"}
