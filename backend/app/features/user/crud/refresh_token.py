import datetime
import uuid

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
    async def get_by_user_and_jti(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        jti: str,
    ) -> UserRefreshToken | None:
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
    ) -> UserRefreshToken:
        now = datetime.datetime.now(datetime.timezone.utc)

        revoke_data = UserRefreshTokenUpdate(
            revoked_at=now,
            replaced_by_jti=new_jti,
            revoked_reason="rotated",
            last_used_at=now,
        )
        await self.update_draft(
            session=session,
            id=current_token.id,
            record=current_token,
            data=revoke_data,
            user=user,
        )

        new_token_data = UserRefreshTokenCreate(
            user_id=current_token.user_id,
            jti=new_jti,
            expires_at=new_expires_at,
        )
        new_token = await self.create_draft(
            session=session,
            data=new_token_data,
            user=user,
        )

        await session.commit()
        await session.refresh(current_token)
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
        now = datetime.datetime.now(datetime.timezone.utc)

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

        now = datetime.datetime.now(datetime.timezone.utc)
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
