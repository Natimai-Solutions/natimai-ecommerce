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
from app.utils.money import reference_price

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

    With ``variants_optional`` the parent is the base configuration, sold and
    priced as is: nothing is rolled up but ``has_variants``.
    """
    variants = await list_variants(session, parent.id)
    parent.has_variants = bool(variants)
    if parent.variants_optional:
        session.add(parent)
        return parent
    priced = [
        v
        for v in variants
        if v.sale_price_cached is not None and v.sale_price_cached > ZERO
    ]
    if priced:
        cheapest = min(priced, key=lambda v: v.sale_price_cached or ZERO)
        parent.sale_price_cached = cheapest.sale_price_cached
        if not any(v.price_extra is not None for v in variants):
            # Variants priced on their own: the parent shows the cheapest.
            # With supplements (R9 / T6) the parent's base_price is the
            # reference the supplements add to: it stays as the admin typed it.
            parent.base_price = cheapest.sale_price_cached or ZERO
        # The listing shows the parent: its margin is the « à partir de » one.
        parent.unit_cost_cached = cheapest.unit_cost_cached
        parent.margin_cached = cheapest.margin_cached
        parent.margin_pct_cached = cheapest.margin_pct_cached
    session.add(parent)
    return parent


def supplemented_price(parent: Product, price_extra: Decimal | None) -> Decimal | None:
    """``parent.base_price + price_extra`` (never negative), None without supplement."""
    if price_extra is None:
        return None
    return reference_price(max(ZERO, (parent.base_price or ZERO) + price_extra))


async def apply_price_extras(session: AsyncSession, parent: Product) -> int:
    """Re-derive the price of every variant carrying a supplement (R9 / T6),
    after the parent's price changed. Returns how many variants moved. The
    caller commits (and rolls the parent up afterwards)."""
    from app.features.product.crud.product import crud_product
    from app.features.product.services.pricing import PricingContext

    variants = [
        v
        for v in await list_variants(session, parent.id, include_inactive=True)
        if v.price_extra is not None
    ]
    changed = []
    for variant in variants:
        price = supplemented_price(parent, variant.price_extra)
        if price is not None and variant.base_price != price:
            variant.base_price = price
            changed.append(variant)
    if changed:
        context = await PricingContext.load(session)
        await crud_product.refresh_cached_prices(
            session, changed, context=context, reason="variant_price_extra"
        )
    return len(changed)


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


# -- a parent is found through its variants ---------------------------------


def active_variants_of_enclosing_product() -> Any:
    """SQL: the active variants of the ``Product`` row of the enclosing query,
    as an aliased select to build a correlated ``EXISTS`` / ``IN`` on.

    A variant may change a characteristic of its parent (« processeur : i7 »
    on an i5 machine): the storefront lists the parent, so what a variant
    carries — its name, its option values, its ``product_specs`` rows — must
    find the parent in the search.
    """
    child = Product.__table__.alias("variant_match")  # type: ignore[attr-defined]
    return child, (
        select(child.c.id)
        .where(
            child.c.parent_product_id == col(Product.id),
            child.c.is_active.is_(True),
            child.c.is_admin_active.is_(True),
        )
        .correlate(Product)
    )


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
            # The base product sold as is has a stock of its own; its
            # optional variants have theirs (what the checkout reserves).
            col(Product.variants_optional).is_(False),
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


def stock_counts_variants(parent: Any) -> bool:
    """Whether a parent's sellable stock includes its variants' (SQL twin:
    :func:`_children_stock_expression`). The base product sold as is
    (``variants_optional``) only counts its own: what the checkout reserves."""
    return bool(getattr(parent, "has_variants", False)) and not bool(
        getattr(parent, "variants_optional", False)
    )
