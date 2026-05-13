"""
Supplier adapter registry.

Add a new distributor by implementing :class:`~app.services.suppliers.base.SupplierAdapter`
and registering it in ``SUPPLIERS`` below. Everything else (orchestrator, ARQ
tasks, HTTP routes, cron scheduling) iterates over this registry.
"""

from __future__ import annotations

from app.services.suppliers.base import (
    NormalizedPricing,
    NormalizedProductData,
    SupplierAdapter,
    SupplierHealth,
)
from app.services.suppliers.ingram_micro import IngramMicroAdapter

# Registered adapter classes keyed by their stable machine name.
SUPPLIERS: dict[str, type[SupplierAdapter]] = {
    IngramMicroAdapter.name: IngramMicroAdapter,
}

# Single shared adapter instance per supplier.
_INSTANCES: dict[str, SupplierAdapter] = {}


class UnknownSupplierError(KeyError):
    """Raised when a supplier name is not present in the registry."""


def supplier_names() -> list[str]:
    """Return the machine names of all registered suppliers."""
    return sorted(SUPPLIERS)


def has_supplier(name: str) -> bool:
    return name in SUPPLIERS


def get_adapter(name: str) -> SupplierAdapter:
    """Return the (cached) adapter instance for ``name``.

    Raises :class:`UnknownSupplierError` if the supplier is not registered.
    """
    if name not in SUPPLIERS:
        raise UnknownSupplierError(name)
    if name not in _INSTANCES:
        _INSTANCES[name] = SUPPLIERS[name]()
    return _INSTANCES[name]


def all_adapters() -> list[SupplierAdapter]:
    """Return one adapter instance per registered supplier."""
    return [get_adapter(name) for name in supplier_names()]


__all__ = [
    "SUPPLIERS",
    "NormalizedPricing",
    "NormalizedProductData",
    "SupplierAdapter",
    "SupplierHealth",
    "UnknownSupplierError",
    "IngramMicroAdapter",
    "all_adapters",
    "get_adapter",
    "has_supplier",
    "supplier_names",
]
