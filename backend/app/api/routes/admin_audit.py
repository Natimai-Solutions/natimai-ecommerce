"""The administrators' audit trail, read-only (R6).

GET /admin/audit-log — most recent first; filters: actor, event, text in
the path, period.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query
from sqlmodel import col, func, select

from app.api.deps import CurrentSuperUser, SessionDep
from app.features.system.models.audit_log import (
    AdminAuditEntry,
    AdminAuditEntryPublic,
    AdminAuditPage,
)

router = APIRouter(prefix="/admin/audit-log", tags=["admin-audit"])


@router.get("", response_model=AdminAuditPage)
async def list_audit_entries(
    session: SessionDep,
    _current_user: CurrentSuperUser,
    actor_id: Annotated[uuid.UUID | None, Query()] = None,
    event: Annotated[str | None, Query(max_length=50)] = None,
    path_contains: Annotated[str | None, Query(max_length=200)] = None,
    since: Annotated[datetime | None, Query()] = None,
    until: Annotated[datetime | None, Query()] = None,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AdminAuditPage:
    filters = []
    if actor_id is not None:
        filters.append(col(AdminAuditEntry.actor_id) == actor_id)
    if event:
        filters.append(col(AdminAuditEntry.event).startswith(event))
    if path_contains:
        filters.append(col(AdminAuditEntry.path).ilike(f"%{path_contains}%"))
    if since is not None:
        filters.append(col(AdminAuditEntry.created_at) >= since)
    if until is not None:
        filters.append(col(AdminAuditEntry.created_at) < until)
    count = (
        await session.exec(
            select(func.count()).select_from(AdminAuditEntry).where(*filters)
        )
    ).one()
    rows = (
        await session.exec(
            select(AdminAuditEntry)
            .where(*filters)
            .order_by(col(AdminAuditEntry.created_at).desc())
            .offset(skip)
            .limit(limit)
        )
    ).all()
    return AdminAuditPage(
        data=[
            AdminAuditEntryPublic.model_validate(r, from_attributes=True) for r in rows
        ],
        count=int(count),
    )
