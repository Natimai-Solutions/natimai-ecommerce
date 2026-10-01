"""Runtime settings: the typed registry behind ``system_settings`` (R5).

A setting the owner may change without a deployment is declared once, as a
:class:`SettingSpec` (type, bounds, category, help text, environment
fallback, public or not, hooks to run when it changes). Its value resolves in
this order:

1. a row of ``system_settings`` (typed in the back-office) — source ``db``;
2. the environment variable named by ``env`` when it was set — source ``env``;
3. the default (the code's default of ``env``, else ``default``) — ``default``.

A blank stored value means « not set »: the fallback applies. A stored value
the spec refuses (a row edited by hand, a bound tightened since) is ignored
and logged — the reader gets the fallback, never a crash.

Reads go through a per-process snapshot of the table: reloaded after
``CACHE_TTL_SECONDS``, at once in the process that writes, and in the other
processes (API replicas, worker) as soon as they see the Redis counter
``settings:version`` move (checked at most every ``VERSION_CHECK_SECONDS``).
A read that must not lag behind a write (the CGV version stamped on an order)
passes ``fresh=True``.

The catalogue of settings lives in ``app.features.system.settings_catalog``
(imported on first use): this module only knows how to type, store and read.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from app.core.config import settings

logger = logging.getLogger(__name__)

Kind = Literal["bool", "int", "float", "decimal", "str", "text", "list"]
Source = Literal["db", "env", "default"]

#: Seconds a process keeps its snapshot before reading the table again.
CACHE_TTL_SECONDS: float = 30.0
#: Seconds between two looks at the Redis counter (writes in other processes).
VERSION_CHECK_SECONDS: float = 3.0
VERSION_KEY = "settings:version"

_TRUE = {"true", "1", "yes", "oui", "on", "vrai"}
_FALSE = {"false", "0", "no", "non", "off", "faux"}


@dataclass(frozen=True)
class SettingSpec:
    """One setting the owner edits from the back-office."""

    key: str
    kind: Kind
    category: str
    label: str
    description: str = ""
    #: Value when neither the base nor ``env`` says anything.
    default: Any = None
    #: Attribute of ``settings`` used as fallback (and whose code default wins
    #: over ``default``). The variable then only seeds/overrides the default.
    env: str | None = None
    #: Readable without authentication (``GET /system/settings``).
    public: bool = False
    minimum: Decimal | None = None
    maximum: Decimal | None = None
    #: Exclusive upper bound (a 100 % commission would divide by zero).
    below: Decimal | None = None
    choices: tuple[str, ...] | None = None
    #: Shown masked in lists and in the audit trail.
    secret: bool = False
    #: Takes effect only after the processes restart.
    restart_required: bool = False
    #: Names of hooks run after a change (see :func:`register_hook`).
    on_change: tuple[str, ...] = ()
    #: Attribute of ``settings`` copied into the base at the first start, when
    #: not blank (legal identity: the base is then the only source).
    seed_env: str | None = None
    #: ``str`` / ``text`` validation: ``email`` or ``url``.
    format: Literal["email", "url"] | None = None
    max_length: int = 5000
    #: Text upper-cased and stripped (codes such as ``TVA_NORMALE``).
    upper: bool = False
    #: Display order inside the category.
    order: int = 0
    #: Extra metadata for the admin screen (unit, placeholder…).
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Resolved:
    """A setting with its effective value and where that value comes from."""

    spec: SettingSpec
    value: Any
    source: Source
    #: The stored text, when the base holds one (blank or not).
    stored: str | None = None
    #: The stored text was refused by the spec (the fallback applies).
    stored_invalid: bool = False
    updated_at: datetime | None = None
    updated_by_id: uuid.UUID | None = None

    @property
    def text(self) -> str:
        return serialize(self.spec, self.value)

    @property
    def fallback_text(self) -> str:
        value, _ = fallback(self.spec)
        return serialize(self.spec, value)


# --------------------------------------------------------------------------
# Registry


_REGISTRY: dict[str, SettingSpec] = {}
_HOOKS: dict[str, Callable[..., Any]] = {}
_catalog_loaded = False


def register(*specs: SettingSpec) -> None:
    for spec in specs:
        if spec.key in _REGISTRY and _REGISTRY[spec.key] != spec:
            raise ValueError(f"Setting {spec.key!r} declared twice")
        _REGISTRY[spec.key] = spec


def register_hook(name: str, fn: Callable[..., Any]) -> None:
    """``fn(session, spec, resolved)`` (sync or async) runs after a change."""
    _HOOKS[name] = fn


def hook(name: str) -> Callable[..., Any] | None:
    _ensure_catalog()
    return _HOOKS.get(name)


def _ensure_catalog() -> None:
    global _catalog_loaded
    if not _catalog_loaded:
        _catalog_loaded = True
        import app.features.system.settings_catalog  # noqa: F401


def specs() -> list[SettingSpec]:
    _ensure_catalog()
    return list(_REGISTRY.values())


def spec_for(key: str) -> SettingSpec | None:
    _ensure_catalog()
    return _REGISTRY.get(key)


def require_spec(key: str) -> SettingSpec:
    spec = spec_for(key)
    if spec is None:
        raise KeyError(key)
    return spec


def public_keys() -> frozenset[str]:
    return frozenset(s.key for s in specs() if s.public)


# --------------------------------------------------------------------------
# Typing


def _number(spec: SettingSpec, raw: Any) -> Decimal:
    text = str(raw).strip().replace(",", ".").replace("%", "").replace(" ", "")
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"« {raw} » n'est pas un nombre") from exc
    if not value.is_finite():
        raise ValueError(f"« {raw} » n'est pas un nombre")
    if spec.minimum is not None and value < spec.minimum:
        raise ValueError(f"la valeur doit être au moins {spec.minimum}, reçu {value}")
    if spec.maximum is not None and value > spec.maximum:
        raise ValueError(f"la valeur doit être au plus {spec.maximum}, reçu {value}")
    if spec.below is not None and value >= spec.below:
        raise ValueError(
            f"la valeur doit être inférieure à {spec.below} (exclu), reçu {value}"
        )
    return value


def parse(spec: SettingSpec, raw: str) -> Any:
    """The typed value of a non-blank text; ``ValueError`` with a French
    message when the spec refuses it."""
    text = str(raw).strip()
    if spec.kind == "bool":
        lowered = text.lower()
        if lowered in _TRUE:
            return True
        if lowered in _FALSE:
            return False
        raise ValueError("la valeur doit être « true » ou « false »")
    if spec.kind == "int":
        number = _number(spec, text)
        if number != number.to_integral_value():
            raise ValueError(f"« {raw} » n'est pas un nombre entier")
        return int(number)
    if spec.kind == "decimal":
        return _number(spec, text)
    if spec.kind == "float":
        return float(_number(spec, text))
    if spec.kind == "list":
        items = [
            part.strip()
            for chunk in text.splitlines()
            for part in chunk.split(",")
            if part.strip()
        ]
        if spec.upper:
            items = [item.upper() for item in items]
        if spec.choices is not None:
            unknown = [item for item in items if item not in spec.choices]
            if unknown:
                raise ValueError(f"valeur(s) inconnue(s) : {', '.join(unknown)}")
        return items
    # str / text
    value = text.upper() if spec.upper else text
    if len(value) > spec.max_length:
        raise ValueError(f"texte trop long ({len(value)} > {spec.max_length})")
    if spec.choices is not None and value not in spec.choices:
        raise ValueError(f"valeur attendue parmi : {', '.join(spec.choices)}")
    if spec.format == "email" and ("@" not in value or " " in value):
        raise ValueError(f"« {value} » n'est pas une adresse e-mail")
    if spec.format == "url" and not value.lower().startswith(("https://", "http://")):
        raise ValueError("l'adresse doit commencer par https://")
    return value


def serialize(spec: SettingSpec, value: Any) -> str:
    """The text stored (and shown) for a typed value."""
    if value is None:
        return ""
    if spec.kind == "bool":
        return "true" if value else "false"
    if spec.kind == "list":
        return ", ".join(str(item) for item in value)
    if spec.kind == "decimal":
        return format(Decimal(str(value)).normalize(), "f")
    if spec.kind == "float":
        number = Decimal(str(value)).normalize()
        return format(number, "f")
    return str(value)


def _coerce_env(spec: SettingSpec, value: Any) -> Any:
    if value is None:
        return None
    if spec.kind == "decimal":
        return Decimal(str(value))
    if spec.kind == "float":
        return float(value)
    if spec.kind == "int":
        return int(value)
    if spec.kind == "bool":
        return bool(value)
    if spec.kind == "list":
        return [str(item) for item in value]
    return str(value)


def fallback(spec: SettingSpec) -> tuple[Any, Source]:
    """The value when the base says nothing: the environment, else the default."""
    if spec.env:
        value = _coerce_env(spec, getattr(settings, spec.env, spec.default))
        source: Source = "env" if spec.env in settings.model_fields_set else "default"
        return value, source
    return spec.default, "default"


def resolve_row(
    spec: SettingSpec,
    stored: str | None,
    *,
    updated_at: datetime | None = None,
    updated_by_id: uuid.UUID | None = None,
) -> Resolved:
    """Resolve one setting from its stored text (``None``: no row)."""
    if stored is not None and stored.strip():
        try:
            return Resolved(
                spec,
                parse(spec, stored),
                "db",
                stored,
                updated_at=updated_at,
                updated_by_id=updated_by_id,
            )
        except ValueError as exc:
            logger.warning("Setting %s: stored value ignored (%s)", spec.key, exc)
            value, source = fallback(spec)
            return Resolved(
                spec, value, source, stored, True, updated_at, updated_by_id
            )
    value, source = fallback(spec)
    return Resolved(spec, value, source, stored, False, updated_at, updated_by_id)


# --------------------------------------------------------------------------
# Snapshot cache


@dataclass
class _Snapshot:
    rows: dict[str, str]
    loaded_at: float
    version: int | None


_snapshot: _Snapshot | None = None
_version_checked_at: float = 0.0
_redis: Any = None


def invalidate_cache() -> None:
    """Forget the snapshot of this process (next read reloads)."""
    global _snapshot
    _snapshot = None


def _redis_client() -> Any:
    global _redis
    if _redis is None:
        import redis.asyncio as redis

        _redis = redis.from_url(  # type: ignore[no-untyped-call]
            str(settings.REDIS_URL), socket_connect_timeout=1, socket_timeout=1
        )
    return _redis


async def _remote_version() -> int | None:
    try:
        raw = await _redis_client().get(VERSION_KEY)
    except Exception:  # noqa: BLE001 - Redis down: the TTL still bounds staleness
        return None
    try:
        return int(raw) if raw is not None else 0
    except (TypeError, ValueError):
        return None


async def bump_version() -> None:
    """Tell the other processes a setting changed (best effort)."""
    try:
        await _redis_client().incr(VERSION_KEY)
    except Exception:  # noqa: BLE001
        logger.info("settings: Redis unreachable, other processes wait the TTL")


async def _load_rows(session: Any | None) -> dict[str, str]:
    """``key → value`` of every row of ``system_settings``."""
    from sqlmodel import select
    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.features.system.models.system_setting import SystemSetting

    stmt = select(SystemSetting.key, SystemSetting.value)
    if session is not None:
        result = await session.exec(stmt)
        return dict(result.all())
    from app.core.db import engine

    async with AsyncSession(engine) as own:
        result = await own.exec(stmt)
        return dict(result.all())


async def _rows(session: Any | None, *, fresh: bool) -> dict[str, str]:
    global _snapshot, _version_checked_at
    now = time.monotonic()
    snap = _snapshot
    if not fresh and snap is not None and now - snap.loaded_at < CACHE_TTL_SECONDS:
        if now - _version_checked_at < VERSION_CHECK_SECONDS:
            return snap.rows
        _version_checked_at = now
        remote = await _remote_version()
        if remote is None or remote == snap.version:
            return snap.rows
    version = await _remote_version()
    _version_checked_at = time.monotonic()
    rows = await _load_rows(session)
    if CACHE_TTL_SECONDS > 0:
        _snapshot = _Snapshot(rows=rows, loaded_at=time.monotonic(), version=version)
    return rows


# --------------------------------------------------------------------------
# Reading


async def resolve(
    key: str, session: Any | None = None, *, fresh: bool = False
) -> Resolved:
    spec = require_spec(key)
    rows = await _rows(session, fresh=fresh)
    return resolve_row(spec, rows.get(key))


async def get(key: str, session: Any | None = None, *, fresh: bool = False) -> Any:
    """The effective, typed value of ``key``."""
    return (await resolve(key, session, fresh=fresh)).value


def peek(key: str) -> Any:
    """Synchronous read for code that cannot await (e-mail rendering): the
    value from this process's last snapshot, else the environment / default.
    Never touches the database."""
    spec = require_spec(key)
    snap = _snapshot
    return resolve_row(spec, snap.rows.get(key) if snap else None).value


async def get_many(
    keys: Iterable[str], session: Any | None = None, *, fresh: bool = False
) -> dict[str, Any]:
    rows = await _rows(session, fresh=fresh)
    return {key: resolve_row(require_spec(key), rows.get(key)).value for key in keys}


__all__ = [
    "CACHE_TTL_SECONDS",
    "Kind",
    "Resolved",
    "SettingSpec",
    "Source",
    "VERSION_CHECK_SECONDS",
    "bump_version",
    "fallback",
    "get",
    "get_many",
    "hook",
    "invalidate_cache",
    "peek",
    "parse",
    "public_keys",
    "register",
    "register_hook",
    "require_spec",
    "resolve",
    "resolve_row",
    "serialize",
    "spec_for",
    "specs",
]
