import datetime
import uuid

from sqlmodel import Field

from app.features.base.models import Base, BaseCreate, BaseUpdate


class UserRefreshTokenBase(Base):
    user_id: uuid.UUID = Field(
        foreign_key="users.id",
        index=True,
        description="Owner user ID",
    )
    jti: str = Field(
        max_length=64,
        unique=True,
        index=True,
        description="JWT refresh token identifier",
    )
    expires_at: datetime.datetime = Field(
        index=True,
        description="Refresh token expiry datetime in UTC",
    )
    revoked_at: datetime.datetime | None = Field(
        default=None,
        index=True,
        description="Revocation datetime in UTC",
    )
    replaced_by_jti: str | None = Field(
        default=None,
        max_length=64,
        index=True,
        description="New refresh token jti used after rotation",
    )
    revoked_reason: str | None = Field(
        default=None,
        max_length=120,
        description="Reason for revocation",
    )
    last_used_at: datetime.datetime | None = Field(
        default=None,
        description="Last successful usage datetime in UTC",
    )


class UserRefreshTokenCreate(UserRefreshTokenBase, BaseCreate):
    pass


class UserRefreshTokenUpdate(BaseUpdate):
    revoked_at: datetime.datetime | None = None
    replaced_by_jti: str | None = None
    revoked_reason: str | None = None
    last_used_at: datetime.datetime | None = None


class UserRefreshToken(UserRefreshTokenBase, table=True):
    __tablename__ = "user_refresh_tokens"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
