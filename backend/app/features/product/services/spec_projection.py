"""Spec projection: normalize Icecat technical_specifications into product_spec rows.

Phase 1: reads spec_definitions.yaml once at import time (YAML fallback).
Phase 3: reads SpecDefinition rows from the DB when a session is available.
Called after each Icecat enrichment and by the reproject ARQ job.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterator
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.product.models.product import Product
from app.features.product.models.product_spec import ProductSpec

_YAML_PATH = Path(__file__).parent.parent / "spec_definitions.yaml"
_DECIMAL_PATTERN = re.compile(r"[-+]?\d*\.?\d+")

# YAML fallback — loaded once at module import. Used when no DB session is
# available (sync code, tests) and as the baseline before DB specs are seeded.
with _YAML_PATH.open(encoding="utf-8") as _f:
    _RAW_DEFS: list[dict[str, Any]] = yaml.safe_load(_f)["specs"]


def build_alias_index_from_defs(
    defs: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Build {normalized_alias → spec_def} index for O(1) matching."""
    index: dict[str, dict[str, Any]] = {}
    for spec in defs:
        for alias in spec.get("aliases", []):
            index[alias.strip().lower()] = spec
    return index


# YAML-backed fallback index (used when no session provided)
_ALIAS_INDEX = build_alias_index_from_defs(_RAW_DEFS)


async def _load_defs_from_db(session: AsyncSession) -> list[dict[str, Any]] | None:
    """Load active spec definitions from the DB. Returns None on error."""
    try:
        from app.features.product.models.spec_definition import SpecDefinition

        stmt = select(SpecDefinition).where(SpecDefinition.is_active == True)  # noqa: E712
        result = await session.exec(stmt)
        rows = result.all()
        if not rows:
            return None
        return [
            {
                "key": r.key,
                "label_fr": r.label_fr,
                "type": r.type,
                "unit": r.unit,
                "categories": list(r.categories or []),
                "aliases": list(r.aliases or []),
                "highlight_rank": r.highlight_rank,
                "translations": dict(r.translations or {}),
            }
            for r in rows
        ]
    except Exception:
        return None


def _spec_applies_to_category(spec_def: dict[str, Any], supplier_category: str) -> bool:
    """Return True if spec_def applies to the given supplier category keyword.

    Matching is partial and case-insensitive: "Ordinateur/Serveur" matches
    both "ordinateur" and "serveur" entries in the YAML categories list.
    """
    categories = spec_def.get("categories")
    if not categories:
        return True
    category_lower = supplier_category.lower()
    return any(kw in category_lower for kw in categories)


def _extract_first_decimal(text: str) -> Decimal | None:
    match = _DECIMAL_PATTERN.search(text)
    if match:
        try:
            return Decimal(match.group())
        except InvalidOperation:
            pass
    return None


def _normalize_unit_to_gb(value: Decimal, raw_text: str) -> Decimal:
    """Convert MB → GB if unit suffix detected."""
    lower = raw_text.lower()
    if "mb" in lower or "mio" in lower:
        return (value / Decimal("1024")).quantize(Decimal("0.0001"))
    if "tb" in lower or "tio" in lower:
        return (value * Decimal("1024")).quantize(Decimal("0.0001"))
    return value


def _normalize_unit_to_inch(value: Decimal, raw_text: str) -> Decimal:
    """Convert cm → inch if suffix detected."""
    lower = raw_text.lower()
    if "cm" in lower:
        return (value / Decimal("2.54")).quantize(Decimal("0.0001"))
    return value


def _project_spec_value(
    spec_def: dict[str, Any], raw_value: str
) -> tuple[str | None, Decimal | None]:
    """Return (value_text, value_numeric) for one spec."""
    spec_type = spec_def.get("type", "enum")
    unit = spec_def.get("unit")

    if spec_type == "numeric":
        numeric = _extract_first_decimal(raw_value)
        if numeric is None:
            return None, None
        if unit == "GB":
            numeric = _normalize_unit_to_gb(numeric, raw_value)
        elif unit == "inch":
            numeric = _normalize_unit_to_inch(numeric, raw_value)
        return None, numeric

    # enum
    normalized = raw_value.strip().lower()
    if not normalized:
        return None, None
    return normalized, None


def iter_matched_specs(
    technical_specifications: list[dict[str, Any]],
    *,
    supplier_category: str | None = None,
    alias_index: dict[str, dict[str, Any]] | None = None,
) -> Iterator[tuple[dict[str, Any], str]]:
    """Yield (spec_def, raw_value) for each Icecat entry matching a definition.

    Shared by the projection (normalized values) and the key-spec tiles, which
    need the supplier's original wording (« Intel Core Ultra 5 », not the
    lowercased projection).
    """
    active_index = alias_index if alias_index is not None else _ALIAS_INDEX

    for item in technical_specifications:
        if not isinstance(item, dict):
            continue

        name = item.get("name") or item.get("label") or item.get("feature") or ""
        value = item.get("value") or item.get("presentation_value") or ""
        name_lower = str(name).strip().lower()
        value_str = str(value).strip()

        if not name_lower or not value_str:
            continue

        spec_def = active_index.get(name_lower)
        if spec_def is None:
            # Partial match: only allow aliases of 4+ chars to avoid "os" → false positives
            for alias, candidate in active_index.items():
                if len(alias) >= 4 and (alias in name_lower or name_lower in alias):
                    spec_def = candidate
                    break

        if spec_def is None:
            continue

        # Skip specs that don't apply to this product's category
        if supplier_category and not _spec_applies_to_category(
            spec_def, supplier_category
        ):
            continue

        yield spec_def, value_str


def project_specs_from_payload(
    technical_specifications: list[dict[str, Any]],
    *,
    supplier_category: str | None = None,
    alias_index: dict[str, dict[str, Any]] | None = None,
) -> dict[str, tuple[str | None, Decimal | None, str | None]]:
    """Return {spec_key → (value_text, value_numeric, unit)} from raw Icecat payload.

    alias_index: override the YAML-backed default index (used when DB
    definitions have been loaded for the current request).
    """
    results: dict[str, tuple[str | None, Decimal | None, str | None]] = {}
    for spec_def, value_str in iter_matched_specs(
        technical_specifications,
        supplier_category=supplier_category,
        alias_index=alias_index,
    ):
        key = spec_def["key"]
        # First match wins for each key
        if key in results:
            continue

        vtext, vnumeric = _project_spec_value(spec_def, value_str)
        if vtext is not None or vnumeric is not None:
            results[key] = (vtext, vnumeric, spec_def.get("unit"))

    return results


async def upsert_product_specs(
    session: AsyncSession,
    product: Product,
) -> int:
    """Project Icecat payload into product_spec rows. Returns count of upserted rows."""
    specs_payload = product.technical_specifications or []
    supplier_category = getattr(product, "supplier_category", None) or ""

    # Prefer DB definitions (editable via admin); fall back to YAML on error.
    db_defs = await _load_defs_from_db(session)
    if db_defs:
        alias_index = build_alias_index_from_defs(db_defs)
        projected = project_specs_from_payload(
            specs_payload,
            supplier_category=supplier_category or None,
            alias_index=alias_index,
        )
    else:
        projected = project_specs_from_payload(
            specs_payload,
            supplier_category=supplier_category or None,
        )

    if not projected:
        return 0

    # Fetch existing specs for this product
    existing_stmt = select(ProductSpec).where(ProductSpec.product_id == product.id)
    existing_result = await session.exec(existing_stmt)
    existing_by_key: dict[str, ProductSpec] = {
        row.spec_key: row for row in existing_result.all()
    }

    upserted = 0
    for spec_key, (value_text, value_numeric, unit) in projected.items():
        if spec_key in existing_by_key:
            row = existing_by_key[spec_key]
            row.value_text = value_text
            row.value_numeric = value_numeric
            row.unit = unit
            session.add(row)
        else:
            row = ProductSpec(
                id=uuid.uuid4(),
                product_id=product.id,
                spec_key=spec_key,
                value_text=value_text,
                value_numeric=value_numeric,
                unit=unit,
            )
            session.add(row)
        upserted += 1

    return upserted


def get_spec_definitions() -> list[dict[str, Any]]:
    """Return the YAML-backed spec definitions list (sync fallback)."""
    return _RAW_DEFS


async def get_effective_spec_definitions(
    session: AsyncSession,
    *,
    category_keyword: str | None = None,
) -> list[dict[str, Any]]:
    """Return the active spec definitions, DB-first with YAML fallback.

    Used by facet endpoints so that admin edits (label, activation, category
    scoping) are reflected. Inactive specs are already excluded by the DB query.
    When ``category_keyword`` is provided, only specs applicable to that
    category are returned (specs with no category restriction always apply).
    """
    defs = await _load_defs_from_db(session)
    if not defs:
        defs = _RAW_DEFS
    if category_keyword:
        defs = [d for d in defs if _spec_applies_to_category(d, category_keyword)]
    return [_localized_def(d) for d in defs]


def _localized_def(definition: dict[str, Any]) -> dict[str, Any]:
    """The definition with its label in the request's language (R9 / T3).

    Facets and key-spec tiles are storefront reads; the back-office edits the
    definitions through their own admin routes, which never come here.
    """
    from app.core.content_i18n import SPEC_DEFINITION_FIELDS, translated_values
    from app.core.i18n import request_locale

    texts = translated_values(
        definition.get("translations"), SPEC_DEFINITION_FIELDS, request_locale()
    )
    if not texts:
        return definition
    return {**definition, **texts}
