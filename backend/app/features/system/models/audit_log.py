"""Journal of what administrators do (R6).

One row per state-changing request (POST / PUT / PATCH / DELETE) made by a
superuser, and per administrator sign-in event (success, wrong password,
wrong second factor, two-factor changes). Request bodies are **not** kept:
they may carry passwords, IBANs or supplier logins. The route template, its
path parameters and the query string say what was touched.

The actor is copied (id and e-mail) rather than referenced: the trail
survives the deletion of the account.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel
from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class AdminAuditEntry(SQLModel, table=True):
    __tablename__ = "admin_audit_log"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), index=True
    )
    actor_id: uuid.UUID | None = Field(default=None, index=True)
    actor_email: str | None = Field(default=None, max_length=255)
    #: ``http`` for a request, ``auth.*`` for a sign-in / two-factor event.
    event: str = Field(default="http", max_length=50, index=True)
    method: str | None = Field(default=None, max_length=10)
    path: str | None = Field(default=None, max_length=500)
    #: Route template (``/api/v1/admin/suppliers/{code}``), to group actions.
    route: str | None = Field(default=None, max_length=300)
    status_code: int | None = Field(default=None)
    ip: str | None = Field(default=None, max_length=64)
    user_agent: str | None = Field(default=None, max_length=300)
    details: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))


class AdminAuditEntryPublic(BaseModel):
    id: uuid.UUID
    created_at: datetime
    actor_id: uuid.UUID | None
    actor_email: str | None
    event: str
    method: str | None
    path: str | None
    route: str | None
    status_code: int | None
    ip: str | None
    details: dict[str, Any] | None = None


class AdminAuditPage(BaseModel):
    data: list[AdminAuditEntryPublic]
    count: int


__all__ = ["AdminAuditEntry", "AdminAuditEntryPublic", "AdminAuditPage"]
