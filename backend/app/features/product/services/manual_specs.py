"""Characteristics typed by hand (R9 / T4).

The storefront filters (``product_specs``) were fed by the Icecat projection
only, so a manual product had none. The product form now shows one row per
spec definition that applies to the product's category, typed (numeric with
its unit, or a list of values), and writes it to ``product_specs`` with
``source = manual`` — a row the projection never rewrites.
"""

from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.product.models.category import Category
from app.features.product.models.product import Product
from app.features.product.models.product_spec import (
    SPEC_SOURCE_ICECAT,
    SPEC_SOURCE_MANUAL,
    ProductSpec,
)
from app.features.product.services.spec_projection import (
    _project_spec_value,
    _spec_applies_to_category,
    get_effective_spec_definitions,
)

#: How many distinct values are suggested for a list spec.
_SUGGESTIONS_LIMIT = 30


class SpecFormRow(BaseModel):
    """One characteristic of the form: its definition and the current value."""

    key: str
    label: str
    type: str
    unit: str | None = None
    value_text: str | None = None
    value_numeric: Decimal | None = None
    #: ``manual``, ``icecat`` or ``None`` when the product has no value yet.
    source: str | None = None
    #: Values other products carry for this key (list specs): typing help.
    suggestions: list[str] = Field(default_factory=list)


class SpecFormResponse(BaseModel):
    product_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    specs: list[SpecFormRow] = Field(default_factory=list)


class SpecValueWrite(BaseModel):
    """A value typed in the form; blank removes the product's row."""

    key: str = Field(max_length=64)
    value: str | None = Field(default=None, max_length=256)


async def _category_keyword(
    session: AsyncSession, product: Product | None, category_id: uuid.UUID | None
) -> str:
    """What the spec definitions' ``categories`` keywords are matched against:
    the supplier's category when the product has one, else the shop
    category's name — a manual product rarely has a supplier category."""
    parts: list[str] = []
    if product is not None and product.supplier_category:
        parts.append(product.supplier_category)
    cat_id = category_id or (product.category_id if product is not None else None)
    if cat_id is not None:
        category = await session.get(Category, cat_id)
        if category is not None:
            parts.append(category.display_name or category.name)
    return " / ".join(parts)


async def _suggestions(session: AsyncSession, keys: list[str]) -> dict[str, list[str]]:
    if not keys:
        return {}
    rows = (
        await session.exec(
            select(
                col(ProductSpec.spec_key),
                col(ProductSpec.value_text),
                func.count(col(ProductSpec.product_id)).label("cnt"),
            )
            .where(
                col(ProductSpec.spec_key).in_(keys),
                col(ProductSpec.value_text).is_not(None),
            )
            .group_by(col(ProductSpec.spec_key), col(ProductSpec.value_text))
            .order_by(col(ProductSpec.spec_key), func.count().desc())
        )
    ).all()
    out: dict[str, list[str]] = {}
    for key, value, _count in rows:
        bucket = out.setdefault(str(key), [])
        if len(bucket) < _SUGGESTIONS_LIMIT and value:
            bucket.append(str(value))
    return out


async def spec_form_rows(
    session: AsyncSession,
    *,
    product: Product | None,
    category_id: uuid.UUID | None,
) -> SpecFormResponse:
    """The rows of the « Caractéristiques » section of the product form."""
    keyword = await _category_keyword(session, product, category_id)
    definitions = [
        d
        for d in await get_effective_spec_definitions(session)
        if not keyword or _spec_applies_to_category(d, keyword)
    ]
    current: dict[str, ProductSpec] = {}
    if product is not None:
        current = {
            row.spec_key: row
            for row in (
                await session.exec(
                    select(ProductSpec).where(ProductSpec.product_id == product.id)
                )
            ).all()
        }
    enum_keys = [d["key"] for d in definitions if d.get("type") != "numeric"]
    suggestions = await _suggestions(session, enum_keys)
    specs = []
    for d in definitions:
        row = current.get(d["key"])
        specs.append(
            SpecFormRow(
                key=d["key"],
                label=d["label_fr"],
                type=d.get("type") or "enum",
                unit=d.get("unit"),
                value_text=row.value_text if row else None,
                value_numeric=row.value_numeric if row else None,
                source=row.source if row else None,
                suggestions=suggestions.get(d["key"], []),
            )
        )
    return SpecFormResponse(
        product_id=product.id if product is not None else None,
        category_id=category_id
        or (product.category_id if product is not None else None),
        specs=specs,
    )


def _typed_value(
    definition: dict[str, Any], raw: str
) -> tuple[str | None, Decimal | None]:
    """The stored value of ``raw`` for the definition; ``ValueError`` when a
    numeric spec gets text."""
    if definition.get("type") == "numeric":
        text = raw.strip().replace(",", ".").replace(" ", "")
        try:
            number = Decimal(text)
        except InvalidOperation as exc:
            raise ValueError(
                f"{definition['label_fr']} : « {raw} » n'est pas un nombre"
            ) from exc
        if not number.is_finite():
            raise ValueError(f"{definition['label_fr']} : nombre invalide")
        return None, number
    # Same normalisation as the Icecat projection, so facets merge.
    value_text, _ = _project_spec_value({**definition, "type": "enum"}, raw)
    return value_text, None


async def apply_manual_specs(
    session: AsyncSession, product: Product, items: list[SpecValueWrite]
) -> int:
    """Write the typed values as ``manual`` rows (blank: the row is removed,
    whatever its source — the admin is correcting a wrong value). Unknown keys
    are refused (``KeyError``), bad numbers too (``ValueError``). Returns the
    number of rows kept."""
    definitions = {d["key"]: d for d in await get_effective_spec_definitions(session)}
    existing = {
        row.spec_key: row
        for row in (
            await session.exec(
                select(ProductSpec).where(ProductSpec.product_id == product.id)
            )
        ).all()
    }
    kept = 0
    for item in items:
        definition = definitions.get(item.key)
        if definition is None:
            raise KeyError(item.key)
        raw = (item.value or "").strip()
        row = existing.get(item.key)
        if not raw:
            if row is not None:
                await session.delete(row)
            continue
        value_text, value_numeric = _typed_value(definition, raw)
        if value_text is None and value_numeric is None:
            if row is not None:
                await session.delete(row)
            continue
        if row is None:
            row = ProductSpec(id=uuid.uuid4(), product_id=product.id, spec_key=item.key)
        row.value_text = value_text
        row.value_numeric = value_numeric
        row.unit = definition.get("unit")
        row.source = SPEC_SOURCE_MANUAL
        session.add(row)
        kept += 1
    return kept


__all__ = [
    "SPEC_SOURCE_ICECAT",
    "SpecFormResponse",
    "SpecFormRow",
    "SpecValueWrite",
    "apply_manual_specs",
    "spec_form_rows",
]
