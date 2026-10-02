"""System settings endpoints (typed registry, R5).

Public:
  GET /system/config   — territory profile, mode and currency of the shop
  GET /system/settings — the settings declared public (legal identity, …)

Admin:
  GET    /admin/system-settings             — every declared setting, resolved
  GET    /admin/system-settings/categories  — the categories, in display order
  GET    /admin/system-settings/{key}       — one setting
  PUT    /admin/system-settings/{key}       — store a value (validated)
  DELETE /admin/system-settings/{key}       — back to the environment / default

Only declared keys are accepted (``settings_catalog.py``), plus the module
switches (``module.<key>``, kept for compatibility: Admin → Modules has its
own endpoint).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter
from fastapi import status as http_status
from pydantic import BaseModel

from app.api.deps import CurrentSuperUser, SessionDep
from app.core import runtime_settings as rs
from app.core.captcha import captcha_site_key
from app.core.config import settings
from app.core.errors import AppError
from app.core.i18n import get_default_locale, get_offered_locales
from app.features.system.models.system_setting import (
    SystemSettingPublic,
    SystemSettingUpdate,
)
from app.features.system.modules import SETTING_PREFIX as MODULE_PREFIX
from app.features.system.modules import (
    enabled_modules,
    parse_switch,
    set_module,
    spec_for,
)
from app.features.system.settings_service import (
    SettingRow,
    get_setting,
    list_settings,
    reset_setting,
    shown,
    write_setting,
)

router = APIRouter(tags=["system"])


class ShopConfigPublic(BaseModel):
    """What every client may know about this deployment (no secrets)."""

    shop_mode: str
    territory_profile: str
    territory_label: str
    reference_currency: str
    country_code: str
    tax_territory_code: str
    shop_name: str
    #: Effective state of every switchable module (Admin → Modules).
    modules: dict[str, bool] = {}
    #: Language when the visitor states none, and the languages offered
    #: (BCP 47, default first) — R7 / L5.
    default_locale: str = "fr"
    available_locales: list[str] = ["fr", "en"]
    #: IANA time zone of the dates shown to customers.
    timezone: str = "Pacific/Tahiti"
    #: Display currency proposed to a visitor who chose none.
    default_display_currency: str = "XPF"
    #: Cloudflare Turnstile site key of the public forms; None = no captcha.
    captcha_site_key: str | None = None


class RuntimeSettingPublic(BaseModel):
    """One declared setting, its effective value and where it comes from."""

    key: str
    category: str
    label: str
    description: str
    #: ``bool``, ``int``, ``float``, ``decimal``, ``str``, ``text`` or ``list``.
    type: str
    #: Effective value as text (masked for a secret).
    value: str
    #: ``db`` (typed in the back-office), ``env`` or ``default``.
    source: str
    #: What applies without a stored value (masked for a secret).
    fallback: str
    #: Environment variable behind the fallback, if any.
    env_var: str | None = None
    #: The stored text was refused (hand edit, bound tightened): ignored.
    stored_invalid: bool = False
    public: bool = False
    secret: bool = False
    restart_required: bool = False
    reprices: bool = False
    choices: list[str] | None = None
    minimum: Decimal | None = None
    maximum: Decimal | None = None
    below: Decimal | None = None
    max_length: int | None = None
    unit: str | None = None
    order: int = 0
    updated_at: datetime | None = None
    updated_by_email: str | None = None


class SettingCategoryPublic(BaseModel):
    key: str
    label: str
    hint: str


class PublicSetting(BaseModel):
    key: str
    value: str


def _public(row: SettingRow) -> RuntimeSettingPublic:
    r = row.resolved
    spec = r.spec
    return RuntimeSettingPublic(
        key=spec.key,
        category=spec.category,
        label=spec.label,
        description=spec.description,
        type=spec.kind,
        value=shown(spec, r.text) or "",
        source=r.source,
        fallback=shown(spec, r.fallback_text) or "",
        env_var=spec.env,
        stored_invalid=r.stored_invalid,
        public=spec.public,
        secret=spec.secret,
        restart_required=spec.restart_required,
        reprices="reprice" in spec.on_change,
        choices=list(spec.choices) if spec.choices else None,
        minimum=spec.minimum,
        maximum=spec.maximum,
        below=spec.below,
        max_length=spec.max_length if spec.kind in ("str", "text") else None,
        unit=spec.extra.get("unit"),
        order=spec.order,
        updated_at=r.updated_at if r.source == "db" or r.stored else None,
        updated_by_email=row.updated_by_email,
    )


@router.get("/system/config", response_model=ShopConfigPublic)
async def get_shop_config(session: SessionDep) -> ShopConfigPublic:
    """Territory and mode of the shop, for the storefront and the admin."""
    profile = settings.territory_profile
    return ShopConfigPublic(
        shop_mode=settings.SHOP_MODE,
        territory_profile=profile.code,
        territory_label=profile.label,
        reference_currency=settings.REFERENCE_CURRENCY,
        country_code=settings.SHOP_COUNTRY_CODE,
        tax_territory_code=settings.TAX_TERRITORY_CODE,
        shop_name=await rs.get("shop_name", session),
        modules=await enabled_modules(session),
        default_locale=await get_default_locale(session),
        available_locales=await get_offered_locales(session),
        timezone=settings.SHOP_TIMEZONE,
        default_display_currency=str(
            await rs.get("default_display_currency", session)
            or settings.REFERENCE_CURRENCY
        ),
        captcha_site_key=(await captcha_site_key(session)) or None,
    )


@router.get("/system/settings", response_model=list[PublicSetting])
async def get_public_settings(session: SessionDep) -> list[PublicSetting]:
    """The public settings that have a value (no auth required)."""
    keys = sorted(rs.public_keys())
    values = await rs.get_many(keys, session)
    out = []
    for key in keys:
        text = rs.serialize(rs.require_spec(key), values[key])
        if text.strip():
            out.append(PublicSetting(key=key, value=text))
    return out


@router.get("/admin/system-settings", response_model=list[RuntimeSettingPublic])
async def admin_list_settings(
    session: SessionDep, _current_user: CurrentSuperUser
) -> list[RuntimeSettingPublic]:
    """Every declared setting, resolved (superuser only)."""
    return [_public(row) for row in await list_settings(session)]


@router.get(
    "/admin/system-settings/categories", response_model=list[SettingCategoryPublic]
)
async def admin_list_setting_categories(
    _current_user: CurrentSuperUser,
) -> list[SettingCategoryPublic]:
    from app.features.system.settings_catalog import CATEGORIES

    return [
        SettingCategoryPublic(key=key, label=label, hint=hint)
        for key, (label, hint) in CATEGORIES.items()
    ]


@router.get("/admin/system-settings/{key}", response_model=RuntimeSettingPublic)
async def admin_get_setting(
    key: str, session: SessionDep, _current_user: CurrentSuperUser
) -> RuntimeSettingPublic:
    return _public(await get_setting(session, key))


async def _put_module_switch(session: Any, key: str, value: str) -> SystemSettingPublic:
    from datetime import timezone

    spec = spec_for(key.removeprefix(MODULE_PREFIX))  # 404 on an unknown module
    lowered = value.strip().lower()
    if lowered not in {"true", "false"}:
        raise AppError(
            code="system_setting.invalid_value",
            status_code=http_status.HTTP_400_BAD_REQUEST,
            message="Un interrupteur de module vaut « true » ou « false »",
            details={"key": key, "value": value},
        )
    await set_module(session, spec.key, parse_switch(lowered, False))
    await session.commit()
    return SystemSettingPublic(
        key=key,
        value=lowered,
        description=spec.label,
        updated_at=datetime.now(timezone.utc),
    )


@router.put(
    "/admin/system-settings/{key}",
    response_model=RuntimeSettingPublic | SystemSettingPublic,
)
async def admin_upsert_setting(
    key: str,
    data: SystemSettingUpdate,
    session: SessionDep,
    current_user: CurrentSuperUser,
) -> RuntimeSettingPublic | SystemSettingPublic:
    """Store a value (blank: back to the fallback).

    Validated against its declaration (400), journaled, and followed by its
    hooks — a pricing parameter re-prices the catalogue in the background.
    A secret sent back masked is left unchanged.
    """
    if key.startswith(MODULE_PREFIX):
        return await _put_module_switch(session, key, data.value)
    actor_id = getattr(current_user, "id", None)
    actor_email = getattr(current_user, "email", None)
    return _public(
        await write_setting(
            session, key, data.value, actor_id=actor_id, actor_email=actor_email
        )
    )


@router.delete("/admin/system-settings/{key}", response_model=RuntimeSettingPublic)
async def admin_reset_setting(
    key: str, session: SessionDep, current_user: CurrentSuperUser
) -> RuntimeSettingPublic:
    """Forget the stored value: the environment variable or the default applies."""
    actor_id = getattr(current_user, "id", None)
    actor_email = getattr(current_user, "email", None)
    return _public(
        await reset_setting(session, key, actor_id=actor_id, actor_email=actor_email)
    )
