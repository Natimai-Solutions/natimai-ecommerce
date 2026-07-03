"""
Supplier integration abstraction.

This module defines the contract every distributor/wholesaler integration must
implement (``SupplierAdapter``) plus the supplier-agnostic DTOs the sync
orchestrator consumes (``NormalizedProductData``, ``NormalizedPricing``).

Each adapter is responsible for:
- talking to its own API (auth strategy, endpoints, paging, rate limiting)
- normalizing payloads into the common DTOs below

The orchestrator, ARQ tasks and HTTP routes only ever see the common DTOs and
this interface, never a vendor-specific shape.
"""

from __future__ import annotations

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


class SupplierAdapter(ABC):
    """Contract implemented by every supplier integration.

    Concrete adapters are registered in :mod:`app.services.suppliers` and looked
    up by :attr:`name`.
    """

    #: Stable machine identifier, e.g. ``"ingram_micro"``. Used in URLs, the
    #: ``supplier_name`` columns and the registry key.
    name: str = ""
    #: Human friendly label, e.g. ``"Ingram Micro"``.
    display_name: str = ""
    #: Categories synced by default when the caller does not pass an explicit
    #: list.
    default_categories: list[str] = []
    #: Stable :class:`~app.features.place.models.Place` ``code`` identifying
    #: where this supplier ships from. The orchestrator resolves it to a
    #: ``Product.supplier_place_id`` (the logistics first leg). ``None`` = unknown.
    origin_place_code: str | None = None
    #: Max number of SKUs accepted per price/availability request.
    price_batch_size: int = 50
    #: Soft client-side rate limit hint (requests / minute). ``None`` = unknown.
    requests_per_minute: int | None = None

    # -- configuration ----------------------------------------------------

    @abstractmethod
    def is_configured(self) -> bool:
        """Return ``True`` when the adapter has everything it needs to run."""

    @abstractmethod
    def is_sync_enabled(self) -> bool:
        """Return ``True`` when scheduled syncing is enabled for this supplier."""

    def config_summary(self) -> dict[str, Any]:
        """Return a credential-free description of the current configuration."""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "configured": self.is_configured(),
            "sync_enabled": self.is_sync_enabled(),
            "default_categories": list(self.default_categories),
        }

    def sync_interval_hours(self) -> int:
        """Hours between scheduled catalog syncs (0 disables the cron job)."""
        return 0

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
