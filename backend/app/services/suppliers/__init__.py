"""
Supplier adapter registry and runtime resolution.

Two levels:

* **implementations** — ``ADAPTERS`` maps an ``adapter_key`` to a
  :class:`~app.services.suppliers.base.SupplierAdapter` subclass. Add a new
  distributor API by implementing the contract and registering the class here.
* **suppliers** — rows of the ``suppliers`` table. Only a row of kind ``api``
  whose ``adapter_key`` is registered yields a live adapter
  (:func:`resolve_adapter`); manual and file suppliers have none, their
  products are created by hand or imported from a file.

Adapter instances are cached per supplier code and rebuilt when the row
changes (``updated_at``), so an OAuth token survives between two jobs while a
configuration edit in the admin takes effect on the next call.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.integrations.models.supplier import (
    AdapterDescriptor,
    Supplier,
    SupplierKind,
)
from app.services.suppliers.base import (
    NormalizedPricing,
    NormalizedProductData,
    SupplierAdapter,
    SupplierConfig,
    SupplierHealth,
)
from app.services.suppliers.ingram_micro import IngramMicroAdapter

# Registered implementations keyed by their stable adapter key.
ADAPTERS: dict[str, type[SupplierAdapter]] = {
    IngramMicroAdapter.adapter_key: IngramMicroAdapter,
}

# One adapter instance per supplier code, invalidated by the row's updated_at.
_INSTANCES: dict[str, tuple[datetime | None, SupplierAdapter]] = {}


class UnknownSupplierError(KeyError):
    """Raised when a supplier code is not present in the database."""


class UnknownAdapterError(KeyError):
    """Raised when an ``adapter_key`` has no registered implementation."""


def adapter_keys() -> list[str]:
    """Return the keys of all registered implementations."""
    return sorted(ADAPTERS)


def has_adapter(adapter_key: str | None) -> bool:
    """Check whether an implementation is registered under ``adapter_key``."""
    return bool(adapter_key) and adapter_key in ADAPTERS


def describe_adapters() -> list[AdapterDescriptor]:
    """Describe every registered implementation (for the admin supplier form)."""
    return [
        AdapterDescriptor(
            key=key,
            display_name=cls.display_name or key,
            configured=cls.credentials_present(),
            settings_keys=list(cls.settings_keys),
        )
        for key, cls in sorted(ADAPTERS.items())
    ]


def build_adapter(config: SupplierConfig) -> SupplierAdapter:
    """Instantiate the implementation named by ``config.adapter_key``.

    Raises :class:`UnknownAdapterError` when no implementation is registered.
    """
    key = config.adapter_key or ""
    if key not in ADAPTERS:
        raise UnknownAdapterError(key)
    return ADAPTERS[key](config)


def adapter_for_supplier(supplier: Supplier) -> SupplierAdapter:
    """Return the (cached) adapter bound to a ``Supplier`` row of kind ``api``.

    Raises :class:`UnknownAdapterError` for an unregistered ``adapter_key``.
    """
    cached = _INSTANCES.get(supplier.code)
    if cached is not None and cached[0] == supplier.updated_at:
        return cached[1]
    adapter = build_adapter(SupplierConfig.from_row(supplier))
    _INSTANCES[supplier.code] = (supplier.updated_at, adapter)
    return adapter


def forget_adapter(code: str) -> None:
    """Drop a cached instance (after the row was deleted)."""
    _INSTANCES.pop(code, None)


async def load_supplier(
    session: AsyncSession, code: str, *, include_inactive: bool = False
) -> Supplier | None:
    """Fetch the supplier row for ``code`` (active only, by default)."""
    statement = select(Supplier).where(Supplier.code == code)
    if not include_inactive:
        statement = statement.where(col(Supplier.is_active).is_(True))
    result = await session.exec(statement)
    return result.first()


async def list_suppliers(
    session: AsyncSession, *, include_inactive: bool = False
) -> list[Supplier]:
    """Return every supplier row, ordered by name."""
    statement = select(Supplier).order_by(col(Supplier.name).asc())
    if not include_inactive:
        statement = statement.where(col(Supplier.is_active).is_(True))
    result = await session.exec(statement)
    return list(result.all())


def is_api_supplier(supplier: Supplier | None) -> bool:
    """Whether a row can yield a live adapter."""
    return (
        supplier is not None
        and supplier.kind == SupplierKind.API
        and has_adapter(supplier.adapter_key)
    )


async def resolve_adapter(session: AsyncSession, code: str) -> SupplierAdapter | None:
    """Return the live adapter for supplier ``code``, or ``None``.

    ``None`` covers every case where nothing can be fetched: unknown or
    inactive code, manual or file supplier, unregistered implementation.
    Callers that need to tell those apart load the row themselves.
    """
    supplier = await load_supplier(session, code)
    if not is_api_supplier(supplier):
        return None
    assert supplier is not None  # narrowed by is_api_supplier
    return adapter_for_supplier(supplier)


async def api_suppliers(session: AsyncSession) -> list[tuple[Supplier, Any]]:
    """Every active API-backed supplier with its adapter (for the scheduler)."""
    pairs: list[tuple[Supplier, Any]] = []
    for supplier in await list_suppliers(session):
        if is_api_supplier(supplier):
            pairs.append((supplier, adapter_for_supplier(supplier)))
    return pairs


__all__ = [
    "ADAPTERS",
    "IngramMicroAdapter",
    "NormalizedPricing",
    "NormalizedProductData",
    "SupplierAdapter",
    "SupplierConfig",
    "SupplierHealth",
    "UnknownAdapterError",
    "UnknownSupplierError",
    "adapter_for_supplier",
    "adapter_keys",
    "api_suppliers",
    "build_adapter",
    "describe_adapters",
    "forget_adapter",
    "has_adapter",
    "is_api_supplier",
    "list_suppliers",
    "load_supplier",
    "resolve_adapter",
]
