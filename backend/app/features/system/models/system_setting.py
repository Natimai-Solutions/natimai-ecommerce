"""System-level runtime settings stored in the database."""

import uuid
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


class SystemSetting(SQLModel, table=True):
    """One key/value pair of a system-wide configuration setting."""

    __tablename__ = "system_settings"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    key: str = Field(max_length=100, unique=True, index=True)
    value: str = Field(max_length=1000)
    description: str | None = Field(default=None, max_length=500)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SystemSettingPublic(SQLModel):
    key: str
    value: str
    description: str | None = None
    updated_at: datetime


class SystemSettingUpdate(SQLModel):
    value: str
    description: str | None = None
