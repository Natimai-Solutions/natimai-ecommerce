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
    #: What an **existing** simple shop showed before the switches existed
    #: (the seed keeps it, so an upgrade hides nothing that was in use).
    legacy_simple: bool = False
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
        key="suppliers",
        label="Fournisseurs et synchronisations",
        description=(
            "Déclarer des fournisseurs, synchroniser leurs catalogues et "
            "rattacher des articles à leurs références. Éteint : écran "
            "Fournisseurs et bloc Approvisionnement masqués, synchronisations "
            "planifiées en pause."
        ),
        group="Approvisionnement",
        simple_default=True,
        legacy_simple=True,
    ),
    ModuleSpec(
        key="file_import",
        label="Import de catalogue (CSV / Excel)",
        description="Importer le catalogue d'un fournisseur depuis un fichier.",
        group="Approvisionnement",
        simple_default=True,
        legacy_simple=True,
    ),
    ModuleSpec(
        key="supplier_orders",
        label="Commandes fournisseurs",
        description=(
            "Commandes passées automatiquement aux fournisseurs à "
            "l'encaissement, et leur suivi."
        ),
        group="Approvisionnement",
    ),
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
    ModuleSpec(
        key="specs",
        label="Caractéristiques filtrables",
        description=(
            "Caractéristiques techniques (processeur, mémoire…) comme filtres "
            "du catalogue, et leur écran de réglage."
        ),
        group="Catalogue",
    ),
    ModuleSpec(
        key="quotes",
        label="Devis",
        description=(
            "Demandes de devis des clients, devis émis et commande au prix du "
            "devis. Éteint : plus de nouvelle demande, onglet Devis masqué."
        ),
        group="Ventes",
        legacy_simple=True,
    ),
    ModuleSpec(
        key="deposits",
        label="Acompte à la commande",
        description=(
            "Paiement d'un acompte à la commande et du solde à réception, "
            "selon le groupe tarifaire. Éteint : tout est payé à la commande."
        ),
        group="Ventes",
        legacy_simple=True,
    ),
    ModuleSpec(
        key="abandoned_carts",
        label="Relance des paniers abandonnés",
        description="Suivi des paniers abandonnés et e-mail de relance.",
        group="Ventes",
        legacy_simple=True,
    ),
    ModuleSpec(
        key="price_groups",
        label="Groupes tarifaires côté client",
        description=(
            "Onglet « Groupe tarifaire » du compte client et demandes de "
            "changement de groupe. Les groupes et leurs prix restent actifs."
        ),
        group="Tarifs",
        legacy_simple=True,
    ),
    ModuleSpec(
        key="customs",
        label="Douane par catégorie",
        description="Taux de douane par catégorie pour les articles importés.",
        group="Tarifs",
    ),
    ModuleSpec(
        key="currencies",
        label="Devises et taux de change",
        description="Écran des taux de change (prix fournisseurs en devises).",
        group="Tarifs",
    ),
    ModuleSpec(
        key="logistics_multileg",
        label="Trajets et lieux",
        description=(
            "Logistique à plusieurs étapes : lieux, trajets, tronçons "
            "d'acheminement. Éteint : écran masqué (la livraison continue)."
        ),
        group="Logistique",
    ),
    ModuleSpec(
        key="grouped_departures",
        label="Départs groupés",
        description=(
            "Départs groupés : commandes rattachées à un départ, bandeau du "
            "prochain départ en vitrine, rappels. Éteint : plus de "
            "rattachement ni de bandeau."
        ),
        group="Logistique",
        legacy_simple=True,
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


def seed_rows(*, existing_shop: bool = False) -> list[SystemSetting]:
    """One row per switch, at the value of the current ``SHOP_MODE`` preset.

    ``existing_shop``: a simple shop that already took orders keeps what it
    showed before the switches existed (:attr:`ModuleSpec.legacy_simple`).
    """

    def _value(spec: ModuleSpec) -> bool:
        if existing_shop and settings.is_simple_shop:
            return spec.legacy_simple
        return spec.preset

    return [
        SystemSetting(
            key=spec.setting_key,
            value="true" if _value(spec) else "false",
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
