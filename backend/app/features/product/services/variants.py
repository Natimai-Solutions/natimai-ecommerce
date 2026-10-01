"""Product variants: a variant is a ``products`` row attached to a parent.

The parent (``has_variants``) is what the storefront lists and what the
product page opens; the customer picks option values (taille, couleur…) and
the chosen variant — a product row of its own — is what goes into the cart,
the order, the invoice and the stock movements. Nothing downstream needs to
know about variants. This module owns the parent ↔ variants bookkeeping:
naming, option axes, the price roll-up shown on the parent, and the queries
the storefront and the admin need.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import case, func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.product.models.product import Product

ZERO = Decimal("0.00")


def variant_display_name(parent_name: str, options: dict[str, str] | None) -> str:
    """« T-shirt — M / Noir » : what the cart, the order and the invoice print."""
    values = [str(v).strip() for v in (options or {}).values() if str(v).strip()]
    return f"{parent_name} — {' / '.join(values)}" if values else parent_name


def option_axes(variants: list[Any]) -> list[str]:
    """Option names across variants, in first-seen order (the selector order)."""
    axes: list[str] = []
    for variant in variants:
        for key in getattr(variant, "variant_options", None) or {}:
            if key not in axes:
                axes.append(key)
    return axes


def variant_conditions(
    parent_id: uuid.UUID, *, include_inactive: bool = False
) -> list[Any]:
    conditions: list[Any] = [col(Product.parent_product_id) == parent_id]
    if not include_inactive:
        conditions.append(col(Product.is_active).is_(True))
        conditions.append(col(Product.is_admin_active).is_(True))
    return conditions


async def list_variants(
    session: AsyncSession, parent_id: uuid.UUID, *, include_inactive: bool = False
) -> list[Product]:
    """Variants of a parent, stable order (creation)."""
    rows = await session.exec(
        select(Product)
        .where(*variant_conditions(parent_id, include_inactive=include_inactive))
        .order_by(col(Product.created_at).asc(), col(Product.name).asc())
    )
    return list(rows.all())


async def refresh_parent_from_variants(
    session: AsyncSession, parent: Product
) -> Product:
    """Roll the variants up onto the parent (no commit).

    The parent is never sold, but the listings sort and filter on its price:
    it shows « à partir de » = the cheapest active variant. ``has_variants``
    follows whether any active variant is left.
    """
    variants = await list_variants(session, parent.id)
    parent.has_variants = bool(variants)
    priced = [
        v
        for v in variants
        if v.sale_price_cached is not None and v.sale_price_cached > ZERO
    ]
    if priced:
        cheapest = min(priced, key=lambda v: v.sale_price_cached or ZERO)
        parent.sale_price_cached = cheapest.sale_price_cached
        parent.base_price = cheapest.sale_price_cached or ZERO
        # The listing shows the parent: its margin is the « à partir de » one.
        parent.unit_cost_cached = cheapest.unit_cost_cached
        parent.margin_cached = cheapest.margin_cached
        parent.margin_pct_cached = cheapest.margin_pct_cached
    session.add(parent)
    return parent


async def refresh_all_parents(session: AsyncSession) -> int:
    """Roll up every parent (after a bulk price refresh); returns how many."""
    parent_ids = (
        await session.exec(
            select(col(Product.parent_product_id))
            .where(col(Product.parent_product_id).is_not(None))
            .distinct()
        )
    ).all()
    count = 0
    for parent_id in parent_ids:
        parent = await session.get(Product, parent_id)
        if parent is None:
            continue
        await refresh_parent_from_variants(session, parent)
        count += 1
    return count


# -- availability of a parent = its variants ---------------------------------


def _children_stock_expression(kind: str) -> Any:
    """SQL: warehouse (``local``) or supplier (``supplier``) sellable stock of
    the active variants of the enclosing product row; 0 for a plain product."""
    from app.features.inventory.models.inventory import Inventory

    child = Product.__table__.alias("variant")  # type: ignore[attr-defined]
    if kind == "local":
        per_variant: Any = (
            select(func.coalesce(func.sum(col(Inventory.quantity)), 0))
            .where(
                col(Inventory.product_id) == child.c.id,
                col(Inventory.place_id).is_(None),
                col(Inventory.is_active).is_(True),
            )
            .correlate(child)
            .scalar_subquery()
        )
    else:
        per_variant = case(
            (
                (child.c.is_supplier_managed.is_(True))
                | (func.coalesce(child.c.supplier_name, "") != ""),
                child.c.supplier_quantity,
            ),
            else_=0,
        )
    return (
        select(func.coalesce(func.sum(per_variant), 0))
        .select_from(child)
        .where(
            child.c.parent_product_id == col(Product.id),
            child.c.is_active.is_(True),
            child.c.is_admin_active.is_(True),
        )
        .correlate(Product)
        .scalar_subquery()
    )


def children_local_quantity_expression() -> Any:
    """SQL: warehouse stock of the active variants of the enclosing row."""
    return _children_stock_expression("local")


def children_supplier_quantity_expression() -> Any:
    """SQL: supplier stock of the active variants of the enclosing row."""
    return _children_stock_expression("supplier")


def children_available_quantity_expression() -> Any:
    """SQL: sellable stock of the active variants of the enclosing product row.

    Same rule as a plain product (warehouse row + supplier stock when the
    variant has a supplier), summed over the variants; 0 for a plain product.
    """
    return (
        children_local_quantity_expression() + children_supplier_quantity_expression()
    )


@dataclass(frozen=True)
class ChildrenStock:
    """Active variants of a parent and their sellable stock, by location."""

    count: int = 0
    local: Decimal = ZERO
    supplier: Decimal = ZERO

    @property
    def total(self) -> Decimal:
        return self.local + self.supplier


async def children_availability(
    session: AsyncSession, parent_ids: list[uuid.UUID]
) -> dict[uuid.UUID, ChildrenStock]:
    """Per parent: active variants and their warehouse / supplier stock."""
    if not parent_ids:
        return {}
    from app.features.inventory.services.availability import (
        local_quantities,
        supplier_available_quantity,
    )

    rows = await session.exec(
        select(Product).where(
            col(Product.parent_product_id).in_(parent_ids),
            col(Product.is_active).is_(True),
            col(Product.is_admin_active).is_(True),
        )
    )
    variants = list(rows.all())
    local = await local_quantities(session, (v.id for v in variants))
    out: dict[uuid.UUID, ChildrenStock] = {}
    for variant in variants:
        parent_id = variant.parent_product_id
        assert parent_id is not None
        current = out.get(parent_id, ChildrenStock())
        out[parent_id] = ChildrenStock(
            count=current.count + 1,
            local=current.local + local.get(variant.id, ZERO),
            supplier=current.supplier + supplier_available_quantity(variant),
        )
    return out
