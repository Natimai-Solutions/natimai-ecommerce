from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel, UniqueConstraint


class UserOAuthLink(SQLModel, table=True):
    """Persistent link between a local User and a social OAuth identity.

    One user can have multiple links (Google + Microsoft).
    One (provider, provider_user_id) pair is globally unique.
    """

    __tablename__ = "user_oauth_links"
    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id", name="uq_oauth_provider_uid"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True, ondelete="CASCADE")
    provider: str = Field(max_length=50, index=True)
    provider_user_id: str = Field(max_length=255)
    email_at_link: str = Field(max_length=255)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class UserOAuthLinkPublic(SQLModel):
    id: uuid.UUID
    user_id: uuid.UUID
    provider: str
    email_at_link: str
    created_at: datetime
