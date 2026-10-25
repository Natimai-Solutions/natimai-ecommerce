import datetime
import uuid

from sqlalchemy import update
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.user.models.refresh_token import (
    UserRefreshToken,
    UserRefreshTokenCreate,
    UserRefreshTokenUpdate,
)
from app.features.user.models.user import User


class CrudUserRefreshToken(
    CrudBase[UserRefreshToken, UserRefreshTokenCreate, UserRefreshTokenUpdate]
):
    """Represents crud user refresh token."""

    async def get_by_user_and_jti(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        jti: str,
    ) -> UserRefreshToken | None:
        """Get by user and jti."""
        statement = select(self.model).where(
            self.model.user_id == user_id,
            self.model.jti == jti,
            col(self.model.is_active).is_(True),
            col(self.model.is_admin_active).is_(True),
        )
        exec_result = await session.exec(statement)
        return exec_result.first()

    async def create_for_user(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        jti: str,
        expires_at: datetime.datetime,
        user: User | None = None,
    ) -> UserRefreshToken:
        """Create for user."""
        token_data = UserRefreshTokenCreate(
            user_id=user_id,
            jti=jti,
            expires_at=expires_at,
        )
        return await self.create(session=session, data=token_data, user=user)

    async def rotate_token(
        self,
        session: AsyncSession,
        *,
        current_token: UserRefreshToken,
        new_jti: str,
        new_expires_at: datetime.datetime,
        user: User | None = None,
    ) -> UserRefreshToken | None:
        """Replace ``current_token`` by a new one; ``None`` if it was already used.

        The revocation is a conditional ``UPDATE … WHERE revoked_at IS NULL``:
        of two concurrent refreshes with the same cookie, only one gets the
        row back. The other one is a reuse — the caller revokes the family —
        instead of a second live session silently forked off the first.
        """
        now = datetime.datetime.now(datetime.UTC)
        token_id = current_token.id
        user_id = current_token.user_id
        claimed = (
            await session.exec(
                update(UserRefreshToken)
                .where(
                    col(UserRefreshToken.id) == token_id,
                    col(UserRefreshToken.revoked_at).is_(None),
                )
                .values(
                    revoked_at=now,
                    replaced_by_jti=new_jti,
                    revoked_reason="rotated",
                    last_used_at=now,
                )
                .returning(col(UserRefreshToken.id))
            )
        ).first()
        if claimed is None:
            await session.rollback()
            return None

        new_token = await self.create_draft(
            session=session,
            data=UserRefreshTokenCreate(
                user_id=user_id, jti=new_jti, expires_at=new_expires_at
            ),
            user=user,
        )
        await session.commit()
        await session.refresh(new_token)
        return new_token

    async def revoke_token(
        self,
        session: AsyncSession,
        *,
        token: UserRefreshToken,
        reason: str,
        replaced_by_jti: str | None = None,
        user: User | None = None,
    ) -> UserRefreshToken:
        """Execute revoke token."""
        now = datetime.datetime.now(datetime.UTC)

        update_data = UserRefreshTokenUpdate(
            revoked_at=now,
            replaced_by_jti=replaced_by_jti,
            revoked_reason=reason,
            last_used_at=now,
        )
        return await self.update(
            session=session,
            id=token.id,
            record=token,
            data=update_data,
            user=user,
        )

    async def revoke_all_active_for_user(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        reason: str,
    ) -> int:
        """Execute revoke all active for user."""
        statement = select(self.model).where(
            self.model.user_id == user_id,
            col(self.model.revoked_at).is_(None),
            col(self.model.is_active).is_(True),
            col(self.model.is_admin_active).is_(True),
        )
        exec_result = await session.exec(statement)
        active_tokens = exec_result.all()
        if not active_tokens:
            return 0

        now = datetime.datetime.now(datetime.UTC)
        for token in active_tokens:
            token.revoked_at = now
            token.revoked_reason = reason
            token.last_used_at = now
            session.add(token)

        await session.commit()
        return len(active_tokens)


crud_user_refresh_token = CrudUserRefreshToken(
    model=UserRefreshToken,
    schema_create=UserRefreshTokenCreate,
    schema_update=UserRefreshTokenUpdate,
    order_by=UserRefreshToken.created_at,
)
