"""Key-spec tiles of the product page (« Core Ultra 5 », « 16 Go », « 512 Go », « 14" »).

Which specs are highlighted, and in what order, is data: ``highlight_rank`` on
the spec definitions (admin-editable, seeded from spec_definitions.yaml). A
product shows the first ``MAX_KEY_SPECS`` highlighted specs it actually has a
projected value for, so a tile never shows an invented or empty value.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.product.models.product import Product
from app.features.product.models.product_spec import ProductKeySpec, ProductSpec
from app.features.product.services.spec_projection import (
    build_alias_index_from_defs,
    get_effective_spec_definitions,
    iter_matched_specs,
)

MAX_KEY_SPECS = 4

_TRAILING_PARENS = re.compile(r"\s*\([^)]*\)\s*$")


def tile_label(label_fr: str) -> str:
    """« Mémoire RAM (Go) » → « Mémoire RAM » : the unit is already in the value."""
    return _TRAILING_PARENS.sub("", label_fr).strip() or label_fr


def _french_number(value: Decimal) -> str:
    """16 → « 16 », 15.6000 → « 15,6 » (French decimal comma, no trailing zeros)."""
    normalized = value.normalize()
    text = f"{normalized:f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",")


def format_numeric(value: Decimal, unit: str | None) -> str:
    """Storefront wording of a projected numeric value, in its canonical unit."""
    if unit == "GB":
        if value >= 1024:
            return f"{_french_number(value / Decimal(1024))} To"
        return f"{_french_number(value)} Go"
    if unit == "inch":
        return f"{_french_number(value)} pouces"
    if unit:
        return f"{_french_number(value)} {unit}"
    return _french_number(value)


def format_text(raw_value: str | None, projected: str | None) -> str | None:
    """Supplier's wording when available, else the (lowercased) projection."""
    if raw_value and raw_value.strip():
        return raw_value.strip()
    if projected:
        return projected[:1].upper() + projected[1:]
    return None


def select_key_specs(
    defs: list[dict[str, Any]],
    stored: dict[str, ProductSpec],
    raw_values: dict[str, str],
    *,
    limit: int = MAX_KEY_SPECS,
) -> list[ProductKeySpec]:
    """Highlighted specs in rank order, keeping only those the product has."""
    highlighted = sorted(
        (d for d in defs if d.get("highlight_rank") is not None),
        key=lambda d: (d["highlight_rank"], d["key"]),
    )
    tiles: list[ProductKeySpec] = []
    for spec_def in highlighted:
        row = stored.get(spec_def["key"])
        if row is None:
            continue
        if row.value_numeric is not None:
            value: str | None = format_numeric(
                Decimal(row.value_numeric), row.unit or spec_def.get("unit")
            )
        else:
            value = format_text(raw_values.get(spec_def["key"]), row.value_text)
        if not value:
            continue
        tiles.append(
            ProductKeySpec(
                key=spec_def["key"], label=tile_label(spec_def["label_fr"]), value=value
            )
        )
        if len(tiles) == limit:
            break
    return tiles


async def compute_key_specs(
    session: AsyncSession, product: Product
) -> list[ProductKeySpec]:
    """Key-spec tiles for one product (empty list when nothing is highlighted)."""
    defs = await get_effective_spec_definitions(session)
    keys = [d["key"] for d in defs if d.get("highlight_rank") is not None]
    if not keys:
        return []

    rows = await session.exec(
        select(ProductSpec).where(
            col(ProductSpec.product_id) == product.id,
            col(ProductSpec.spec_key).in_(keys),
        )
    )
    stored = {row.spec_key: row for row in rows.all()}
    if not stored:
        return []

    # The projection lowercases text values; go back to the supplier's wording.
    raw_values: dict[str, str] = {}
    for spec_def, raw in iter_matched_specs(
        product.technical_specifications or [],
        supplier_category=product.supplier_category or None,
        category_id=product.category_id,
        alias_index=build_alias_index_from_defs(defs),
    ):
        raw_values.setdefault(spec_def["key"], raw)

    return select_key_specs(defs, stored, raw_values)
