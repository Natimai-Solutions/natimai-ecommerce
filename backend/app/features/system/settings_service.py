"""Writing runtime settings from the back-office, and seeding them (R5).

:func:`write_setting` is the only way the API changes a setting: the key must
be declared, the value pass its spec (400 otherwise), the row records who
changed it, the audit trail keeps the old and new values (masked for a
secret), every process forgets its snapshot, and the spec's hooks run
(re-pricing the catalogue, for instance).
"""

from __future__ import annotations

import inspect
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core import runtime_settings as rs
from app.core.config import settings
from app.core.errors import AppError
from app.features.system.models.system_setting import SystemSetting

logger = logging.getLogger(__name__)

MASK = "••••••"


def unknown_key(key: str) -> AppError:
    return AppError(
        code="system_setting.unknown_key",
        status_code=404,
        message=f"Réglage inconnu : {key}",
        details={"key": key},
    )


def _spec(key: str) -> rs.SettingSpec:
    spec = rs.spec_for(key)
    if spec is None:
        raise unknown_key(key)
    return spec


def shown(spec: rs.SettingSpec, text: str | None) -> str | None:
    """What the admin and the journal may see of a stored text."""
    if text is None:
        return None
    if spec.secret and text.strip():
        return MASK
    return text


@dataclass(frozen=True)
class SettingRow:
    resolved: rs.Resolved
    updated_by_email: str | None = None


async def list_settings(session: AsyncSession) -> list[SettingRow]:
    """Every declared setting, resolved from the table read now (no cache)."""
    from app.features.user.models.user import User

    rows = {
        row.key: row
        for row in (
            await session.exec(
                select(SystemSetting).where(
                    col(SystemSetting.key).in_([s.key for s in rs.specs()])
                )
            )
        ).all()
    }
    author_ids = {r.updated_by_id for r in rows.values() if r.updated_by_id}
    emails: dict[uuid.UUID, str] = {}
    if author_ids:
        users = await session.exec(select(User).where(col(User.id).in_(author_ids)))
        emails = {u.id: u.email for u in users.all()}
    result = []
    for spec in rs.specs():
        row = rows.get(spec.key)
        resolved = rs.resolve_row(
            spec,
            row.value if row else None,
            updated_at=row.updated_at if row else None,
            updated_by_id=row.updated_by_id if row else None,
        )
        result.append(
            SettingRow(
                resolved,
                emails.get(row.updated_by_id) if row and row.updated_by_id else None,
            )
        )
    return result


async def get_setting(session: AsyncSession, key: str) -> SettingRow:
    spec = _spec(key)
    for row in await list_settings(session):
        if row.resolved.spec.key == spec.key:
            return row
    raise unknown_key(key)  # pragma: no cover - declared keys are listed


async def _run_hooks(session: AsyncSession, spec: rs.SettingSpec) -> None:
    if not spec.on_change:
        return
    resolved = await rs.resolve(spec.key, session, fresh=True)
    for name in spec.on_change:
        fn = rs.hook(name)
        if fn is None:
            logger.warning("Setting %s: unknown hook %s", spec.key, name)
            continue
        try:
            outcome = fn(session, spec, resolved)
            if inspect.isawaitable(outcome):
                await outcome
        except Exception:  # noqa: BLE001 - the value is saved; report, go on
            logger.exception("Setting %s: hook %s failed", spec.key, name)


async def write_setting(
    session: AsyncSession,
    key: str,
    raw: str | None,
    *,
    actor_id: uuid.UUID | None = None,
    actor_email: str | None = None,
) -> SettingRow:
    """Store ``raw`` for ``key`` (blank or ``None``: back to the fallback).

    Validates against the spec (400 ``system_setting.invalid_value``),
    commits, invalidates the caches, journals and runs the hooks.
    """
    spec = _spec(key)
    text = (raw or "").strip()
    if spec.secret and text == MASK:
        return await get_setting(session, key)  # sent back as shown: unchanged
    stored_text = ""
    if text:
        try:
            value = rs.parse(spec, raw or "")
        except ValueError as exc:
            raise AppError(
                code="system_setting.invalid_value",
                status_code=400,
                message=f"{spec.label} : {exc}",
                details={"key": key},
            ) from exc
        stored_text = rs.serialize(spec, value)

    row = (
        await session.exec(select(SystemSetting).where(SystemSetting.key == key))
    ).first()
    old = row.value if row is not None else None
    if row is None:
        row = SystemSetting(key=key, value=stored_text, description=spec.label[:500])
    row.value = stored_text
    row.updated_at = datetime.now(UTC)
    row.updated_by_id = actor_id
    session.add(row)
    await session.commit()

    rs.invalidate_cache()
    await rs.bump_version()
    if (old or "") != stored_text:
        from app.features.system import audit

        await audit.record(
            event="setting.changed",
            actor_id=actor_id,
            actor_email=actor_email,
            details={
                "key": key,
                "old": shown(spec, old),
                "new": shown(spec, stored_text),
            },
            session=session,
        )
        await _run_hooks(session, spec)
    return await get_setting(session, key)


async def reset_setting(
    session: AsyncSession,
    key: str,
    *,
    actor_id: uuid.UUID | None = None,
    actor_email: str | None = None,
) -> SettingRow:
    """Forget the stored value: the environment or the default applies."""
    return await write_setting(
        session, key, None, actor_id=actor_id, actor_email=actor_email
    )


async def seed_settings(session: AsyncSession) -> int:
    """First start: copy ``seed_env`` values into the base. Never rewrites a
    row that exists (blank or not): the owner is master of the base. Adds,
    no commit. Returns the number of rows created."""
    existing = set(
        (
            await session.exec(
                select(SystemSetting.key).where(
                    col(SystemSetting.key).in_([s.key for s in rs.specs()])
                )
            )
        ).all()
    )
    created = 0
    for spec in rs.specs():
        if spec.key in existing or not spec.seed_env:
            continue
        value = str(getattr(settings, spec.seed_env, "") or "").strip()
        if not value:
            continue
        session.add(
            SystemSetting(key=spec.key, value=value, description=spec.label[:500])
        )
        created += 1
    return created


__all__ = [
    "MASK",
    "SettingRow",
    "get_setting",
    "list_settings",
    "reset_setting",
    "seed_settings",
    "shown",
    "write_setting",
]
