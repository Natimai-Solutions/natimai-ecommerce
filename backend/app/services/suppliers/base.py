"""
Supplier integration abstraction.

This module defines the contract every distributor/wholesaler integration must
implement (``SupplierAdapter``) plus the supplier-agnostic DTOs the sync
orchestrator consumes (``NormalizedProductData``, ``NormalizedPricing``).

An adapter is an *implementation* (how to talk to Ingram, to TechData…). A
*supplier* is a row of the ``suppliers`` table the admin declared, which
names the implementation it uses (``adapter_key``) and carries its non-secret
configuration: origin warehouse, customs regime, categories, cadence. The
adapter instance is built from that row (:class:`SupplierConfig`); credentials
stay in the environment and are checked by :meth:`SupplierAdapter.is_configured`.

Each adapter is responsible for:
- talking to its own API (auth strategy, endpoints, paging, rate limiting)
- normalizing payloads into the common DTOs below

The orchestrator, ARQ tasks and HTTP routes only ever see the common DTOs and
this interface, never a vendor-specific shape.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(slots=True)
class NormalizedProductData:
    """Supplier-agnostic representation of a catalog product.

    Adapters build these from their own API payloads. ``supplier_sku`` is the
    distributor's own identifier for the item (Ingram part number, TechData
    material number, ...).

    ``price`` / ``quantity`` are ``None`` when the source does not carry them
    (Ingram's catalog endpoint returns neither): the orchestrator then leaves
    the persisted cost and stock untouched instead of zeroing them.
    """

    supplier_sku: str
    name: str
    manufacturer: str | None = None
    vendor_part_number: str | None = None
    description: str | None = None
    category: str | None = None
    subcategory: str | None = None
    price: float | Decimal | None = None
    quantity: float | Decimal | None = None
    currency: str | None = None
    weight: float | None = None
    image_url: str | None = None
    spec_url: str | None = None
    upc: str | None = None
    ean: str | None = None
    # Refurbished lots (file suppliers): left None when the source has no
    # such column, so the persisted value is never reset.
    condition: str | None = None
    condition_grade: str | None = None
    battery_health_pct: int | None = None
    os_licence: str | None = None
    warranty_months: int | None = None
    availability_mode: str | None = None
    # Anything that does not map onto a first-class field yet.
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class NormalizedPricing:
    """Supplier-agnostic price & availability snapshot for a single SKU."""

    supplier_sku: str
    price: float | Decimal | None = None
    currency: str | None = None
    quantity: float | Decimal | None = None
    vendor_part_number: str | None = None
    manufacturer: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SupplierHealth:
    """Result of a supplier connectivity / configuration probe."""

    healthy: bool
    configured: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SupplierConfig:
    """Snapshot of a ``suppliers`` row, detached from the ORM session.

    Built by :meth:`from_row`; adapters read their configuration here and
    never touch the database themselves.
    """

    code: str
    display_name: str
    kind: str = "api"
    adapter_key: str | None = None
    origin_place_id: uuid.UUID | None = None
    is_domestic: bool = False
    sync_enabled: bool = True
    sync_interval_hours: int = 0
    default_categories: list[str] = field(default_factory=list)
    price_currency: str | None = None
    column_mapping: dict[str, str] | None = None
    settings: dict[str, Any] = field(default_factory=dict)
    #: SKUs the admin chose to follow (empty = the whole synced catalog).
    sku_allowlist: list[str] = field(default_factory=list)

    @classmethod
    def from_row(cls, supplier: Any) -> SupplierConfig:
        """Build a config from a ``Supplier`` row (duck-typed for tests)."""
        kind = getattr(supplier, "kind", "api")
        return cls(
            code=str(supplier.code),
            display_name=str(getattr(supplier, "name", supplier.code)),
            kind=str(getattr(kind, "value", kind)),
            adapter_key=getattr(supplier, "adapter_key", None),
            origin_place_id=getattr(supplier, "origin_place_id", None),
            is_domestic=bool(getattr(supplier, "is_domestic", False)),
            sync_enabled=bool(getattr(supplier, "sync_enabled", True)),
            sync_interval_hours=int(getattr(supplier, "sync_interval_hours", 0) or 0),
            default_categories=list(
                getattr(supplier, "default_categories", None) or []
            ),
            price_currency=getattr(supplier, "price_currency", None),
            column_mapping=getattr(supplier, "column_mapping", None),
            settings=dict(getattr(supplier, "settings", None) or {}),
            sku_allowlist=list(getattr(supplier, "sku_allowlist", None) or []),
        )


class SupplierAdapter(ABC):
    """Contract implemented by every supplier integration.

    Concrete adapters are registered in :mod:`app.services.suppliers` under
    :attr:`adapter_key` and instantiated per supplier row with a
    :class:`SupplierConfig`. Instantiating without a config (``Adapter()``)
    yields a stand-alone adapter whose code is its ``adapter_key`` — handy in
    tests and for one-off scripts.
    """

    #: Stable identifier of the *implementation*, e.g. ``"ingram_micro"``.
    #: This is the value ``Supplier.adapter_key`` points at.
    adapter_key: str = ""
    #: Human friendly label of the implementation, e.g. ``"Ingram Micro"``.
    display_name: str = ""
    #: Keys the implementation reads in ``Supplier.settings`` (for the admin UI).
    settings_keys: tuple[str, ...] = ()
    #: Max number of SKUs accepted per price/availability request.
    price_batch_size: int = 50
    #: Soft client-side rate limit hint (requests / minute). ``None`` = unknown.
    requests_per_minute: int | None = None

    def __init__(self, config: SupplierConfig | None = None) -> None:
        """Bind the adapter to a supplier configuration."""
        if config is None:
            config = SupplierConfig(
                code=self.adapter_key,
                display_name=self.display_name,
                adapter_key=self.adapter_key,
            )
        self.config = config

    # -- identity ---------------------------------------------------------

    @property
    def name(self) -> str:
        """Supplier code: the value of ``Product.supplier_name`` and the URLs."""
        return self.config.code

    @property
    def supplier_display_name(self) -> str:
        """Label of the supplier row (falls back to the implementation label)."""
        return self.config.display_name or self.display_name

    @property
    def origin_place_id(self) -> uuid.UUID | None:
        """``Place`` the supplier ships from (drives the first logistics leg)."""
        return self.config.origin_place_id

    @property
    def origin_place_code(self) -> str | None:
        """Fallback ``Place.code`` when the supplier row has no origin place.

        Implementations may read it from their settings; the orchestrator
        only uses it when :attr:`origin_place_id` is ``None``.
        """
        code = self.config.settings.get("origin_place_code")
        return str(code) if code else None

    @property
    def is_domestic(self) -> bool:
        """Same customs territory as our warehouse: no customs, no import freight."""
        return self.config.is_domestic

    @property
    def price_currency(self) -> str | None:
        """Currency assumed for prices the source does not qualify."""
        return self.config.price_currency

    @property
    def default_categories(self) -> list[str]:
        """Categories synced by default when the caller passes none."""
        return list(self.config.default_categories)

    @property
    def sku_allowlist(self) -> list[str]:
        """SKUs the admin chose to follow; empty means the whole catalog."""
        return list(self.config.sku_allowlist)

    # -- configuration ----------------------------------------------------

    @classmethod
    def credentials_present(cls) -> bool:
        """Return ``True`` when the environment carries the implementation's secrets.

        Class-level so the admin can list which implementations are usable
        before any supplier row exists.
        """
        return True

    def is_configured(self) -> bool:
        """Return ``True`` when the adapter has everything it needs to run."""
        return self.credentials_present()

    def is_sync_enabled(self) -> bool:
        """Return ``True`` when syncing is enabled for this supplier."""
        return bool(self.config.sync_enabled)

    def sync_interval_hours(self) -> int:
        """Hours between scheduled catalog syncs (0 = never scheduled)."""
        return int(self.config.sync_interval_hours)

    def config_summary(self) -> dict[str, Any]:
        """Return a credential-free description of the current configuration."""
        return {
            "name": self.name,
            "display_name": self.supplier_display_name,
            "adapter_key": self.adapter_key,
            "configured": self.is_configured(),
            "sync_enabled": self.is_sync_enabled(),
            "sync_interval_hours": self.sync_interval_hours(),
            "default_categories": list(self.default_categories),
            "is_domestic": self.is_domestic,
            "origin_place_id": (
                str(self.origin_place_id) if self.origin_place_id else None
            ),
            "settings": dict(self.config.settings),
        }

    # -- catalog ----------------------------------------------------------

    @abstractmethod
    async def fetch_catalog(
        self, category: str, **filters: Any
    ) -> AsyncIterator[list[NormalizedProductData]]:
        """Yield catalog products for ``category`` in pages.

        Implemented as an async generator yielding lists (one page per yield)
        so the orchestrator can commit incrementally without holding the whole
        catalog in memory.
        """
        raise NotImplementedError
        yield  # pragma: no cover - makes this an async generator for typing

    @abstractmethod
    async def fetch_price_and_availability(
        self, skus: list[str]
    ) -> dict[str, NormalizedPricing]:
        """Return price/availability keyed by supplier SKU.

        Callers are expected to chunk ``skus`` into :attr:`price_batch_size`
        slices; adapters may also defensively truncate.
        """

    # -- health -----------------------------------------------------------

    @abstractmethod
    async def health_check(self) -> SupplierHealth:
        """Probe the upstream API and report connectivity/config status."""
