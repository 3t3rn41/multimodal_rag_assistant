from sqlalchemy import func, select, update

from backend.auth.models import AuthSession, EmailChallenge, User
from backend.infrastructure.database.repository import AsyncRepository


class AuthRepository(AsyncRepository):
    async def user_by_email(self, email: str):
        return (
            await self.db.execute(
                select(User).where(User.email == email).with_for_update()
            )
        ).scalar_one_or_none()

    async def lock_user(self, user_id: int):
        return (
            await self.db.execute(
                select(User)
                .where(User.id == user_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()

    async def invalidate_challenges(self, user_id, purpose, now):
        await self.db.execute(
            update(EmailChallenge)
            .where(
                EmailChallenge.user_id == user_id,
                EmailChallenge.purpose == purpose,
            )
            .values(
                consumed_at=func.coalesce(EmailChallenge.consumed_at, now),
                registration_password_hash=None,
                code_hash=None,
            )
        )

    async def challenge_and_user(self, token_hash):
        row = await self.db.get(EmailChallenge, token_hash)
        if row is None:
            return None, None
        user = await self.lock_user(row.user_id)
        row = (
            await self.db.execute(
                select(EmailChallenge)
                .where(EmailChallenge.token_hash == token_hash)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        return row, user

    async def valid_session(self, token_hash, now):
        return (
            await self.db.execute(
                select(AuthSession, User)
                .join(User, User.id == AuthSession.user_id)
                .where(
                    AuthSession.token_hash == token_hash,
                    AuthSession.revoked_at.is_(None),
                    AuthSession.expires_at > now,
                    User.is_active.is_(True),
                    User.email_verified_at.is_not(None),
                )
            )
        ).first()

    async def revoke_all(self, user_id, now):
        await self.db.execute(
            update(AuthSession)
            .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )

    async def revoke(self, token_hash, now):
        await self.db.execute(
            update(AuthSession)
            .where(AuthSession.token_hash == token_hash)
            .values(revoked_at=now)
        )
