"""Publication eligibility for storefront products (audit items F1 / F5).

Two inputs of the CAF price are filled by nobody in the supplier sync and used
to default to a silent zero:

* **customs rate** (F1) — a product with no rate, and whose category carries no
  default either, priced as if customs were 0 %, i.e. 16-30+ points under cost.
* **weight** (F5) — a product with no weight gets a billable weight of 0, so the
  variable import freight vanishes from the CAF base.

Both produce a *plausible but wrong* price rather than an error, which is why
they are gated here instead of being left to the pricing service: a product
whose price cannot be computed truthfully must not be sellable at all.

Dimensions are deliberately **not** required: without them the billable weight
falls back to the real weight, which under-bills bulky-but-light items but never
invents a number. That fallback is the documented behaviour (see the risk table
in PLAN_DE_TRAVAIL.md); only the silent zeros are blocking.

Use ``publication_conditions()`` to filter storefront queries, and
``publication_blockers()`` to explain a single product (cart guard, admin).
"""

from __future__ import annotations

from typing import Any

from sqlmodel import and_, col, or_, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.product.models.category import Category
from app.features.product.models.product import Product

CUSTOMS_RATE_UNRESOLVED = "customs_rate_unresolved"
WEIGHT_MISSING = "weight_missing"


def customs_rate_condition() -> Any:
    """SQL: the product's customs rate resolves, on itself or on its category.

    The category default is read through a correlated subquery so callers do
    not have to add a join to their existing statement.
    """
    category_default_customs = (
        select(col(Category.default_customs_rate_pct))
        .where(col(Category.id) == col(Product.category_id))
        .scalar_subquery()
    )
    return or_(
        col(Product.customs_rate_pct).is_not(None),
        category_default_customs.is_not(None),
    )


def weight_condition() -> Any:
    """SQL: the product has a usable weight for the freight computation."""
    return and_(col(Product.weight).is_not(None), col(Product.weight) > 0)


def publication_conditions() -> list[Any]:
    """SQL conditions a product must satisfy to be shown on the storefront.

    Meant to be spread into an existing ``select(Product).where(...)``.
    """
    return [customs_rate_condition(), weight_condition()]


async def publication_blockers(
    session: AsyncSession,
    product: Product,
) -> list[str]:
    """Return the reasons a product may not be published, empty when publishable."""
    # Imported here: pricing imports nothing from this module, but keeping the
    # dependency one-way and lazy avoids any import cycle as both grow.
    from app.features.product.services.pricing import resolve_customs_rate_pct

    blockers: list[str] = []

    if await resolve_customs_rate_pct(session, product) is None:
        blockers.append(CUSTOMS_RATE_UNRESOLVED)

    weight = getattr(product, "weight", None)
    if weight is None or float(weight) <= 0:
        blockers.append(WEIGHT_MISSING)

    return blockers
