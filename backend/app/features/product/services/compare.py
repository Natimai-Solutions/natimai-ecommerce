"""Product comparator (R8 / confort — commerce): side-by-side specs.

The storefront keeps the shortlist (up to :data:`MAX_COMPARE` products) in
the browser; this service builds the table from the projected specs
(``product_specs``) of those products: one row per spec definition at least
one of them has a value for, the highlighted ones first, in the request's
language. Values are worded as the product page's key-spec tiles.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from sqlmodel import Field, SQLModel, col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.product.models.product import Product, ProductPublic
from app.features.product.models.product_spec import ProductSpec
from app.features.product.services.key_specs import (
    format_numeric,
    format_text,
    tile_label,
)
from app.features.product.services.spec_projection import (
    build_alias_index_from_defs,
    get_effective_spec_definitions,
    iter_matched_specs,
)

MAX_COMPARE = 4


class CompareRow(SQLModel):
    """One spec across the compared products (``values`` keyed by product id,
    None when a product has no value for it)."""

    key: str
    label: str
    values: dict[str, str | None] = Field(default_factory=dict)


class ProductCompareResponse(SQLModel):
    """Response for GET /product/compare."""

    products: list[ProductPublic]
    rows: list[CompareRow]


def _ordered_defs(defs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    highlighted = sorted(
        (d for d in defs if d.get("highlight_rank") is not None),
        key=lambda d: (d["highlight_rank"], d["key"]),
    )
    rest = [d for d in defs if d.get("highlight_rank") is None]
    return [*highlighted, *rest]


async def compare_rows(
    session: AsyncSession, products: Sequence[Product]
) -> list[CompareRow]:
    """Spec rows for ``products``; empty when none has a projected spec."""
    if not products:
        return []
    defs = await get_effective_spec_definitions(session)
    if not defs:
        return []
    ids: list[uuid.UUID] = [p.id for p in products]
    stored: dict[uuid.UUID, dict[str, ProductSpec]] = {pid: {} for pid in ids}
    for row in (
        await session.exec(
            select(ProductSpec).where(col(ProductSpec.product_id).in_(ids))
        )
    ).all():
        stored.setdefault(row.product_id, {})[row.spec_key] = row

    # The projection lowercases text values; go back to the supplier's wording.
    alias_index = build_alias_index_from_defs(defs)
    raw_values: dict[uuid.UUID, dict[str, str]] = {}
    for product in products:
        values: dict[str, str] = {}
        for spec_def, raw in iter_matched_specs(
            product.technical_specifications or [],
            supplier_category=product.supplier_category or None,
            category_id=product.category_id,
            alias_index=alias_index,
        ):
            values.setdefault(spec_def["key"], raw)
        raw_values[product.id] = values

    rows: list[CompareRow] = []
    for spec_def in _ordered_defs(defs):
        key = spec_def["key"]
        values_by_product: dict[str, str | None] = {}
        any_value = False
        for product in products:
            spec = stored.get(product.id, {}).get(key)
            value: str | None = None
            if spec is not None:
                if spec.value_numeric is not None:
                    value = format_numeric(
                        Decimal(spec.value_numeric), spec.unit or spec_def.get("unit")
                    )
                else:
                    value = format_text(
                        raw_values.get(product.id, {}).get(key), spec.value_text
                    )
            values_by_product[str(product.id)] = value or None
            any_value = any_value or bool(value)
        if any_value:
            rows.append(
                CompareRow(
                    key=key,
                    label=tile_label(spec_def["label_fr"]),
                    values=values_by_product,
                )
            )
    return rows
