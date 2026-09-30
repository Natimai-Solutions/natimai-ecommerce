"""Supplier SKU allowlist: « we only sell these references ».

An API supplier such as Ingram exposes tens of thousands of products; the
shop picks the ones it follows. When ``Supplier.sku_allowlist`` is filled,
the catalogue sync writes nothing for other SKUs (nothing is created), the
price / stock refresh only asks for the listed ones, and the products this
supplier manages outside the list leave the storefront. Empty list: the
whole synced catalogue is followed, as before.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.integrations.models.supplier import Supplier
from app.features.product.models.product import Product


def normalize_skus(raw: Iterable[str]) -> list[str]:
    """Trimmed, non-empty, deduplicated (first occurrence wins, order kept)."""
    seen: set[str] = set()
    skus: list[str] = []
    for value in raw:
        sku = str(value).strip()
        if sku and sku not in seen:
            seen.add(sku)
            skus.append(sku)
    return skus


def allowed_sku(allowlist: Iterable[str] | None, sku: str | None) -> bool:
    """True when the list is empty (everything) or names ``sku``."""
    allowed = set(allowlist or ())
    return not allowed or (sku or "") in allowed


def restrict_skus(allowlist: Iterable[str] | None, skus: Iterable[str]) -> list[str]:
    """``skus`` kept in order, minus those outside a non-empty allowlist."""
    allowed = set(allowlist or ())
    return [sku for sku in skus if not allowed or sku in allowed]


class AllowlistEntry(BaseModel):
    """One listed SKU and the product it currently matches, if any."""

    supplier_sku: str
    product_id: str | None = None
    product_name: str | None = None
    is_active: bool | None = None


class AllowlistWrite(BaseModel):
    """The whole list (replaces the previous one; empty clears it)."""

    skus: list[str] = Field(default_factory=list)


class AllowlistView(BaseModel):
    """What the admin sees: the list, what is known, what will come."""

    supplier_name: str
    entries: list[AllowlistEntry] = Field(default_factory=list)
    #: Listed SKUs already in the catalogue.
    known: int = 0
    #: Listed SKUs the next catalogue sync will create.
    unknown: list[str] = Field(default_factory=list)
    #: Products this supplier manages outside the list (hidden from the shop).
    outside: int = 0
    #: Products hidden by the last save (0 on a read).
    deactivated: int = 0


async def _managed_products(session: AsyncSession, supplier_name: str) -> list[Any]:
    result = await session.exec(
        select(Product).where(
            Product.supplier_name == supplier_name,
            col(Product.is_supplier_managed).is_(True),
        )
    )
    return list(result.all())


async def allowlist_view(session: AsyncSession, supplier: Supplier) -> AllowlistView:
    """The supplier's list against its catalogue (read-only)."""
    skus = list(supplier.sku_allowlist or [])
    by_sku = {
        p.supplier_sku: p
        for p in await _managed_products(session, supplier.code)
        if p.supplier_sku
    }
    entries = [
        AllowlistEntry(
            supplier_sku=sku,
            product_id=str(by_sku[sku].id) if sku in by_sku else None,
            product_name=by_sku[sku].name if sku in by_sku else None,
            is_active=bool(by_sku[sku].is_active) if sku in by_sku else None,
        )
        for sku in skus
    ]
    listed = set(skus)
    return AllowlistView(
        supplier_name=supplier.code,
        entries=entries,
        known=sum(1 for sku in skus if sku in by_sku),
        unknown=[sku for sku in skus if sku not in by_sku],
        outside=sum(1 for sku in by_sku if sku not in listed) if listed else 0,
    )


async def save_allowlist(
    session: AsyncSession, supplier: Supplier, raw_skus: Iterable[str]
) -> AllowlistView:
    """Replace the list and hide the supplier's managed products outside it.

    Listed products that are inactive come back on their own: the next
    price / stock refresh re-evaluates ``is_active`` from the thresholds.
    Does not commit.
    """
    skus = normalize_skus(raw_skus)
    supplier.sku_allowlist = skus or None
    supplier.updated_at = datetime.now(timezone.utc)
    session.add(supplier)

    deactivated = 0
    if skus:
        listed = set(skus)
        for product in await _managed_products(session, supplier.code):
            if product.supplier_sku in listed or not product.is_active:
                continue
            product.is_active = False
            session.add(product)
            deactivated += 1
    await session.flush()
    view = await allowlist_view(session, supplier)
    view.deactivated = deactivated
    return view


__all__ = [
    "AllowlistEntry",
    "AllowlistView",
    "AllowlistWrite",
    "allowed_sku",
    "allowlist_view",
    "normalize_skus",
    "restrict_skus",
    "save_allowlist",
]
