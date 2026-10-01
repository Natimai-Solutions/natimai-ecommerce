"""Writing the administrators' audit trail (R6).

:func:`record` never raises: losing an audit line must not fail the action
it describes (it is logged instead). It writes in its own session unless one
is given, so a request's rollback does not erase the trace of the attempt.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete as sa_delete
from sqlmodel import col
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.features.system.models.audit_log import AdminAuditEntry

logger = logging.getLogger(__name__)

#: Methods that change state: the ones journaled.
MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


async def record(
    *,
    event: str,
    actor_id: uuid.UUID | None = None,
    actor_email: str | None = None,
    method: str | None = None,
    path: str | None = None,
    route: str | None = None,
    status_code: int | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    details: dict[str, Any] | None = None,
    session: AsyncSession | None = None,
) -> None:
    entry = AdminAuditEntry(
        event=event[:50],
        actor_id=actor_id,
        actor_email=(actor_email or None) and actor_email[:255],
        method=method,
        path=(path or None) and path[:500],
        route=(route or None) and route[:300],
        status_code=status_code,
        ip=(ip or None) and ip[:64],
        user_agent=(user_agent or None) and user_agent[:300],
        details=details or None,
    )
    try:
        if session is not None:
            session.add(entry)
            await session.commit()
            return
        from app.core.db import engine

        async with AsyncSession(engine) as own:
            own.add(entry)
            await own.commit()
    except Exception:  # noqa: BLE001 - the trail must never break the action
        logger.exception("Audit entry lost: %s %s %s", event, method, path)


#: Query parameters never stored as typed (path parameters are identifiers:
#: kept, they say what was touched).
_REDACTED_KEYS = ("password", "passwd", "token", "secret", "api_key", "apikey", "totp")


def _safe_params(values: dict[str, Any]) -> dict[str, Any]:
    return {
        k: ("***" if any(word in k.lower() for word in _REDACTED_KEYS) else v)
        for k, v in values.items()
    }


async def record_admin_request(
    *,
    user_id: uuid.UUID,
    method: str,
    path: str,
    route: str | None,
    status_code: int,
    path_params: dict[str, Any],
    query: dict[str, Any],
    ip: str | None,
    user_agent: str | None,
) -> None:
    """Journal a state-changing request, if its author is an administrator."""
    from app.core.db import engine
    from app.features.user.models.user import User

    try:
        async with AsyncSession(engine) as session:
            user = await session.get(User, user_id)
            if user is None or not user.is_superuser:
                return
            details: dict[str, Any] = {}
            if path_params:
                details["path_params"] = dict(path_params)
            if query:
                details["query"] = _safe_params(query)
            await record(
                event="http",
                actor_id=user.id,
                actor_email=user.email,
                method=method,
                path=path,
                route=route,
                status_code=status_code,
                ip=ip,
                user_agent=user_agent,
                details=details or None,
                session=session,
            )
    except Exception:  # noqa: BLE001
        logger.exception("Audit of %s %s lost", method, path)


async def purge_older_than(session: AsyncSession, days: int) -> int:
    """Delete entries older than ``days`` (0 or less: keep everything)."""
    if days <= 0:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await session.exec(
        sa_delete(AdminAuditEntry).where(col(AdminAuditEntry.created_at) < cutoff)
    )
    await session.commit()
    return int(result.rowcount or 0)


async def purge_audit_log_task(_ctx: dict[str, Any]) -> dict[str, int]:
    """Daily cron: apply ``AUDIT_LOG_RETENTION_DAYS``."""
    from app.core.db import engine

    async with AsyncSession(engine) as session:
        deleted = await purge_older_than(
            session, int(settings.AUDIT_LOG_RETENTION_DAYS)
        )
    return {"deleted": deleted}


def get_audit_cron_jobs() -> list[Any]:
    from arq import cron

    return [
        cron(
            purge_audit_log_task,  # type: ignore[arg-type]
            hour=4,
            minute=10,
            second=0,
            name="purge_audit_log",
        )
    ]


__all__ = [
    "MUTATING_METHODS",
    "get_audit_cron_jobs",
    "purge_audit_log_task",
    "purge_older_than",
    "record",
]
