"""System-level runtime settings stored in the database."""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Column, ForeignKey, Text, Uuid, event
from sqlalchemy.orm import Session
from sqlmodel import Field, SQLModel


class SystemSetting(SQLModel, table=True):
    """One key/value pair of a system-wide configuration setting."""

    __tablename__ = "system_settings"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    key: str = Field(max_length=100, unique=True, index=True)
    value: str = Field(sa_column=Column(Text, nullable=False))
    description: str | None = Field(default=None, max_length=500)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    #: Administrator of the last change made from the back-office.
    updated_by_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(
            Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
    )


class SystemSettingPublic(SQLModel):
    key: str
    value: str
    description: str | None = None
    updated_at: datetime


class SystemSettingUpdate(SQLModel):
    value: str
    description: str | None = None


# Any committed change to this table (back-office, seed, module switch, test
# fixture…) drops the runtime-settings snapshot of this process and tells
# the other processes (Redis counter), so no writer has to remember to.
def _note_settings_flush(session: Any, _flush_context: Any) -> None:
    touched = (*session.new, *session.dirty, *session.deleted)
    if any(isinstance(obj, SystemSetting) for obj in touched):
        session.info["system_settings_changed"] = True


def _after_commit(session: Any) -> None:
    if not session.info.pop("system_settings_changed", False):
        return
    from app.core import runtime_settings

    runtime_settings.invalidate_cache()
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    task = loop.create_task(runtime_settings.bump_version())
    _pending.add(task)
    task.add_done_callback(_pending.discard)


def _after_rollback(session: Any) -> None:
    session.info.pop("system_settings_changed", None)


_pending: set[asyncio.Task[None]] = set()
event.listen(Session, "after_flush", _note_settings_flush)
event.listen(Session, "after_commit", _after_commit)
event.listen(Session, "after_rollback", _after_rollback)
