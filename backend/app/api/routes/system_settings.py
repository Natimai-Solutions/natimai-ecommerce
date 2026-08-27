"""System settings endpoints.

Public:
  GET /system/settings — whitelisted keys (default_display_currency, …)

Admin:
  GET  /admin/system-settings        — all settings
  GET  /admin/system-settings/{key}  — single setting
  PUT  /admin/system-settings/{key}  — upsert a setting
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi import status as http_status
from sqlmodel import col, select

from app.api.deps import CurrentSuperUser, SessionDep
from app.core.errors import AppError
from app.features.system.legal_identity import LEGAL_SETTING_KEYS
from app.features.system.models.system_setting import (
    SystemSetting,
    SystemSettingPublic,
    SystemSettingUpdate,
)

# Keys exposed to any caller (no auth required).
#
# The legal identity is public by nature — publishing it is a legal obligation,
# and the storefront renders it on the CGV / mentions légales / privacy pages
# without requiring a login.
_PUBLIC_KEYS = frozenset({"default_display_currency"}) | LEGAL_SETTING_KEYS

router = APIRouter(tags=["system"])


@router.get("/system/settings", response_model=list[SystemSettingPublic])
async def get_public_settings(session: SessionDep) -> list[SystemSettingPublic]:
    """Return whitelisted system settings (no auth required)."""
    stmt = select(SystemSetting).where(col(SystemSetting.key).in_(_PUBLIC_KEYS))
    result = await session.exec(stmt)
    rows = result.all()
    return [SystemSettingPublic.model_validate(r) for r in rows]


@router.get("/admin/system-settings", response_model=list[SystemSettingPublic])
async def admin_list_settings(
    session: SessionDep,
    _current_user: CurrentSuperUser,
) -> list[SystemSettingPublic]:
    """Return all system settings (superuser only)."""
    result = await session.exec(select(SystemSetting))
    rows = result.all()
    return [SystemSettingPublic.model_validate(r) for r in rows]


@router.get("/admin/system-settings/{key}", response_model=SystemSettingPublic)
async def admin_get_setting(
    key: str,
    session: SessionDep,
    _current_user: CurrentSuperUser,
) -> SystemSettingPublic:
    stmt = select(SystemSetting).where(SystemSetting.key == key)
    result = await session.exec(stmt)
    row = result.first()
    if row is None:
        raise AppError(
            code="system_setting.not_found",
            status_code=http_status.HTTP_404_NOT_FOUND,
            message=f"Setting '{key}' not found",
            details={"key": key},
        )
    return SystemSettingPublic.model_validate(row)


@router.put("/admin/system-settings/{key}", response_model=SystemSettingPublic)
async def admin_upsert_setting(
    key: str,
    data: SystemSettingUpdate,
    session: SessionDep,
    _current_user: CurrentSuperUser,
) -> SystemSettingPublic:
    """Create or update a system setting."""
    stmt = select(SystemSetting).where(SystemSetting.key == key)
    result = await session.exec(stmt)
    row = result.first()

    if row is None:
        row = SystemSetting(
            id=uuid.uuid4(),
            key=key,
            value=data.value,
            description=data.description,
            updated_at=datetime.now(timezone.utc),
        )
    else:
        row.value = data.value
        if data.description is not None:
            row.description = data.description
        row.updated_at = datetime.now(timezone.utc)

    session.add(row)
    await session.commit()
    await session.refresh(row)
    return SystemSettingPublic.model_validate(row)
