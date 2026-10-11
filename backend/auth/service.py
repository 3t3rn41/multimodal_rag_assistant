import asyncio
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError

from backend.auth.mail import send_password_reset, send_registration_code
from backend.auth.models import AuthSession, EmailChallenge, User
from backend.auth.repository import AuthRepository
from backend.core.config import settings
from backend.core.errors import ServiceError
from backend.core.security.passwords import hash_password, verify_password

SESSION_COOKIE = "mmrag_session"
CSRF_COOKIE = "mmrag_csrf"
REGISTRATION_CODE_MINUTES = 10
REGISTRATION_RESEND_SECONDS = 60
REGISTRATION_MAX_ATTEMPTS = 5
REGISTRATION_PURPOSE = "register_code"
_DUMMY_HASH = hash_password("a-random-dummy-password-that-is-never-an-account")


def utcnow():
    return datetime.now(UTC).replace(tzinfo=None)


def token_hash(token: str):
    return hashlib.sha256(token.encode()).hexdigest()


def registration_code_hash(challenge_hash: str, code: str):
    return hmac.new(
        settings.env.secret_key.encode(),
        f"{REGISTRATION_PURPOSE}:{challenge_hash}:{code}".encode(),
        hashlib.sha256,
    ).hexdigest()


def public_user(user: User):
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "email_verified": bool(user.email_verified_at),
    }


class AuthService:
    def __init__(self, db):
        self.repo = AuthRepository(db)

    async def _issue_password_reset(self, user):
        purpose = "reset_password"
        now, token = utcnow(), secrets.token_urlsafe(32)
        await self.repo.invalidate_challenges(user.id, purpose, now)
        self.repo.add(
            EmailChallenge(
                token_hash=token_hash(token),
                user_id=user.id,
                purpose=purpose,
                expires_at=now + timedelta(minutes=settings.env.auth_token_minutes),
            )
        )
        await self.repo.commit()
        await send_password_reset(user.email, token)

    async def register(self, email: str, password: str):
        registration_token = secrets.token_urlsafe(32)
        password_hash = await asyncio.to_thread(hash_password, password)
        user = await self.repo.user_by_email(email)
        if user is None:
            user = User(
                email=email,
                password_hash=password_hash,
                display_name=email.split("@")[0],
            )
            self.repo.add(user)
            try:
                await self.repo.flush()
            except IntegrityError:
                await self.repo.rollback()
                return registration_token
        if user.is_active and user.email_verified_at is None:
            now = utcnow()
            await self.repo.invalidate_challenges(user.id, REGISTRATION_PURPOSE, now)
            code = f"{secrets.randbelow(1_000_000):06d}"
            challenge_hash = token_hash(registration_token)
            self.repo.add(
                EmailChallenge(
                    token_hash=challenge_hash,
                    user_id=user.id,
                    purpose=REGISTRATION_PURPOSE,
                    expires_at=now + timedelta(minutes=REGISTRATION_CODE_MINUTES),
                    code_hash=registration_code_hash(challenge_hash, code),
                    registration_password_hash=password_hash,
                    failed_attempts=0,
                    created_at=now,
                )
            )
            await self.repo.commit()
            await send_registration_code(email, code, REGISTRATION_CODE_MINUTES)
        else:
            await self.repo.rollback()
        # A random registration handle is returned for all addresses; it is not
        # the emailed code and does not establish ownership or create a session.
        return registration_token

    async def resend_registration(self, email: str, registration_token: str):
        row, user = await self.repo.challenge_and_user(token_hash(registration_token))
        if (
            not row
            or not user
            or user.email != email
            or not user.is_active
            or user.email_verified_at is not None
            or row.purpose != REGISTRATION_PURPOSE
            or not row.registration_password_hash
        ):
            raise ServiceError("注册信息已失效，请返回创建账号页面重新获取验证码。")
        now = utcnow()
        if (now - row.created_at).total_seconds() < REGISTRATION_RESEND_SECONDS:
            raise ServiceError("请等待 60 秒后再获取验证码。", 429)
        code = f"{secrets.randbelow(1_000_000):06d}"
        digest = registration_code_hash(row.token_hash, code)
        while row.code_hash and hmac.compare_digest(row.code_hash, digest):
            code = f"{secrets.randbelow(1_000_000):06d}"
            digest = registration_code_hash(row.token_hash, code)
        row.code_hash = digest
        row.failed_attempts = 0
        row.consumed_at = None
        row.created_at = now
        row.expires_at = now + timedelta(minutes=REGISTRATION_CODE_MINUTES)
        await self.repo.commit()
        await send_registration_code(email, code, REGISTRATION_CODE_MINUTES)

    async def verify_registration(self, email: str, registration_token: str, code: str):
        row, user = await self.repo.challenge_and_user(token_hash(registration_token))
        now = utcnow()
        if (
            not row
            or not user
            or user.email != email
            or not user.is_active
            or user.email_verified_at is not None
            or row.purpose != REGISTRATION_PURPOSE
            or row.consumed_at
            or row.expires_at <= now
            or not row.code_hash
            or not row.registration_password_hash
            or row.failed_attempts >= REGISTRATION_MAX_ATTEMPTS
        ):
            raise ServiceError("验证码已失效或已使用，请重新获取验证码。")
        if not hmac.compare_digest(
            row.code_hash, registration_code_hash(row.token_hash, code)
        ):
            row.failed_attempts += 1
            locked = row.failed_attempts >= REGISTRATION_MAX_ATTEMPTS
            if locked:
                row.consumed_at = now
            await self.repo.commit()
            raise ServiceError(
                "验证码错误次数过多，请重新获取。"
                if locked
                else "验证码不正确，请检查后重试。"
            )
        # Apply only the password bound to this browser's registration handle.
        # A different registration cannot activate a password chosen elsewhere.
        user.password_hash = row.registration_password_hash
        user.email_verified_at = now
        await self.repo.invalidate_challenges(user.id, REGISTRATION_PURPOSE, now)
        await self.repo.revoke_all(user.id, now)
        await self.repo.commit()

    async def request_password_reset(self, email: str):
        user = await self.repo.user_by_email(email)
        if (
            user
            and user.is_active
            and user.email_verified_at is not None
        ):
            await self._issue_password_reset(user)
        else:
            await self.repo.rollback()

    async def reset_password(self, token: str, password: str):
        purpose = "reset_password"
        row, user = await self.repo.challenge_and_user(token_hash(token))
        if (
            row is None
            or user is None
            or not user.is_active
            or user.email_verified_at is None
            or row.purpose != purpose
            or row.consumed_at
            or row.expires_at <= utcnow()
        ):
            raise ServiceError("链接已失效或已使用，请重新申请邮件。")
        user.password_hash = await asyncio.to_thread(hash_password, password)
        row.consumed_at = utcnow()
        await self.repo.invalidate_challenges(user.id, purpose, utcnow())
        await self.repo.revoke_all(user.id, utcnow())
        await self.repo.commit()

    async def login(self, email: str, password: str):
        user = await self.repo.user_by_email(email)
        good = await asyncio.to_thread(
            verify_password, password, user.password_hash if user else _DUMMY_HASH
        )
        if not user or not good or not user.is_active:
            raise ServiceError("邮箱或密码不正确。", 401)
        if not user.email_verified_at:
            raise ServiceError(
                "请先验证邮箱；可在创建账号页面重新获取注册验证码。", 403
            )
        raw, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self.repo.add(
            AuthSession(
                token_hash=token_hash(raw),
                csrf_hash=token_hash(csrf),
                user_id=user.id,
                expires_at=utcnow() + timedelta(days=settings.env.auth_session_days),
            )
        )
        await self.repo.commit()
        return user, raw, csrf

    async def authenticate(self, token):
        if not token or len(token) > 128:
            raise ServiceError("请先登录。", 401)
        row = await self.repo.valid_session(token_hash(token), utcnow())
        if row is None:
            raise ServiceError("登录已失效，请重新登录。", 401)
        return row

    async def logout(self, token):
        await self.repo.revoke(token_hash(token), utcnow())
        await self.repo.commit()
