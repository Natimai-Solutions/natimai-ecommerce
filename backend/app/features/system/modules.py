"""Modules switched on and off from the database (R4 / S6-S7).

``SHOP_MODE`` used to decide, at start-up, which parts of the shop existed: in
``simple`` mode the supplier crons were never scheduled, Icecat never ran and
the admin hid six menus — and going back to ``full`` meant a restart. The
real state now lives in ``system_settings`` (``module.<key>``), one switch per
module, editable from Admin → Système → Modules and read on every use, so a
module comes back **without a restart**.

``SHOP_MODE`` is only a **preset**: it gives the value of a switch that was
never stored, and the seed writes that value once on the first start
(:func:`seed_rows`). After that the stored value wins, whatever the mode.

A switch never deletes anything: a module turned off hides its screens,
refuses its admin routes and makes its crons idle; its data stays in place
for the day it is turned back on.

Reads go through a short per-process cache (:data:`CACHE_TTL_SECONDS`): a
write through :func:`set_module` invalidates it locally, other processes see
the change within the TTL. Until the typed registry of R5 exists, this module
is the registry of the switches.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.features.system.models.system_setting import SystemSetting

SETTING_PREFIX = "module."
CACHE_TTL_SECONDS = 15.0

_TRUE = {"true", "1", "yes", "oui", "on"}
_FALSE = {"false", "0", "no", "non", "off"}


def _icecat_env_allows() -> bool:
    return bool(settings.ICECAT_ENABLED)


@dataclass(frozen=True)
class ModuleSpec:
    """One switchable module."""

    key: str
    label: str
    description: str
    group: str
    #: Value in ``SHOP_MODE=simple`` (``full`` turns every module on).
    simple_default: bool = False
    #: Environment kill switch above the stored value (``None`` = none).
    env_gate: Callable[[], bool] | None = field(default=None, compare=False)
    #: Environment variable named by the admin screen when the gate is closed.
    env_gate_name: str | None = None

    @property
    def setting_key(self) -> str:
        return f"{SETTING_PREFIX}{self.key}"

    @property
    def preset(self) -> bool:
        """The value ``SHOP_MODE`` gives a switch that was never stored."""
        return self.simple_default if settings.is_simple_shop else True

    def env_allows(self) -> bool:
        return self.env_gate is None or bool(self.env_gate())


MODULES: tuple[ModuleSpec, ...] = (
    ModuleSpec(
        key="icecat",
        label="Enrichissement Icecat",
        description=(
            "Fiches techniques, images et caractéristiques récupérées chez "
            "Icecat pour les articles des fournisseurs. Éteint : aucun appel à "
            "Icecat, les articles importés gardent le contenu du fournisseur."
        ),
        group="Intégrations",
        simple_default=False,
        env_gate=_icecat_env_allows,
        env_gate_name="ICECAT_ENABLED",
    ),
)

_BY_KEY: dict[str, ModuleSpec] = {spec.key: spec for spec in MODULES}

_cache: tuple[float, dict[str, bool]] | None = None


def invalidate_cache() -> None:
    """Forget the cached switches (after a write, and in tests)."""
    global _cache
    _cache = None


def spec_for(key: str) -> ModuleSpec:
    try:
        return _BY_KEY[key]
    except KeyError:
        raise AppError(
            code="module.unknown",
            status_code=404,
            message=f"Module inconnu : {key}",
            details={"key": key, "available": sorted(_BY_KEY)},
        ) from None


def parse_switch(raw: str | None, default: bool) -> bool:
    value = (raw or "").strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    return default


async def stored_switches(session: AsyncSession) -> dict[str, bool]:
    """The value of every switch (stored, else its preset), env gates aside."""
    global _cache
    now = time.monotonic()
    if _cache is not None and now - _cache[0] < CACHE_TTL_SECONDS:
        return dict(_cache[1])
    rows = await session.exec(
        select(SystemSetting).where(
            col(SystemSetting.key).in_([spec.setting_key for spec in MODULES])
        )
    )
    stored = {row.key: row.value for row in rows.all()}
    state = {
        spec.key: parse_switch(stored.get(spec.setting_key), spec.preset)
        for spec in MODULES
    }
    _cache = (now, state)
    return dict(state)


async def enabled_modules(session: AsyncSession) -> dict[str, bool]:
    """Effective state of every module: its switch AND its environment gate."""
    state = await stored_switches(session)
    return {spec.key: state[spec.key] and spec.env_allows() for spec in MODULES}


async def module_enabled(session: AsyncSession, key: str) -> bool:
    """Whether module ``key`` is on right now."""
    spec = spec_for(key)
    if not spec.env_allows():
        return False
    return (await stored_switches(session))[key]


async def require_module(session: AsyncSession, key: str) -> None:
    """Raise an explicit 404 when module ``key`` is off."""
    if not await module_enabled(session, key):
        spec = spec_for(key)
        raise AppError(
            code="module.disabled",
            status_code=404,
            message=f"Le module « {spec.label} » est désactivé",
            details={"module": key},
        )


async def set_module(session: AsyncSession, key: str, enabled: bool) -> None:
    """Store a switch. Flushes, no commit; invalidates the local cache."""
    spec = spec_for(key)
    row = (
        await session.exec(
            select(SystemSetting).where(SystemSetting.key == spec.setting_key)
        )
    ).first()
    if row is None:
        row = SystemSetting(key=spec.setting_key, value="", description=spec.label)
    row.value = "true" if enabled else "false"
    session.add(row)
    await session.flush()
    invalidate_cache()


def seed_rows() -> list[SystemSetting]:
    """One row per switch, at the value of the current ``SHOP_MODE`` preset."""
    return [
        SystemSetting(
            key=spec.setting_key,
            value="true" if spec.preset else "false",
            description=f"Module « {spec.label} » (true / false)",
        )
        for spec in MODULES
    ]


__all__ = [
    "CACHE_TTL_SECONDS",
    "MODULES",
    "ModuleSpec",
    "SETTING_PREFIX",
    "enabled_modules",
    "invalidate_cache",
    "module_enabled",
    "parse_switch",
    "require_module",
    "seed_rows",
    "set_module",
    "spec_for",
    "stored_switches",
]
