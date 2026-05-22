"""Spec projection: normalize Icecat technical_specifications into product_spec rows.

Reads spec_definitions.yaml once at import time (small file, ~20 entries).
Called after each Icecat enrichment and by the reproject ARQ job.
"""

from __future__ import annotations

import re
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.product.models.product import Product
from app.features.product.models.product_spec import ProductSpec

_YAML_PATH = Path(__file__).parent.parent / "spec_definitions.yaml"
_DECIMAL_PATTERN = re.compile(r"[-+]?\d*\.?\d+")

# Loaded once at module import
with _YAML_PATH.open(encoding="utf-8") as _f:
    _RAW_DEFS: list[dict[str, Any]] = yaml.safe_load(_f)["specs"]


def _build_alias_index() -> dict[str, dict[str, Any]]:
    """Build {normalized_alias → spec_def} index for O(1) matching."""
    index: dict[str, dict[str, Any]] = {}
    for spec in _RAW_DEFS:
        for alias in spec.get("aliases", []):
            index[alias.strip().lower()] = spec
    return index


_ALIAS_INDEX = _build_alias_index()


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


def project_specs_from_payload(
    technical_specifications: list[dict[str, Any]],
) -> dict[str, tuple[str | None, Decimal | None, str | None]]:
    """Return {spec_key → (value_text, value_numeric, unit)} from raw Icecat payload.

    Skips unrecognized specs silently.
    """
    results: dict[str, tuple[str | None, Decimal | None, str | None]] = {}

    for item in technical_specifications:
        if not isinstance(item, dict):
            continue

        name = item.get("name") or item.get("label") or item.get("feature") or ""
        value = item.get("value") or item.get("presentation_value") or ""
        name_lower = str(name).strip().lower()
        value_str = str(value).strip()

        if not name_lower or not value_str:
            continue

        spec_def = _ALIAS_INDEX.get(name_lower)
        if spec_def is None:
            # Try partial match: check if name_lower contains any alias
            for alias, candidate in _ALIAS_INDEX.items():
                if alias in name_lower or name_lower in alias:
                    spec_def = candidate
                    break

        if spec_def is None:
            continue

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
    projected = project_specs_from_payload(specs_payload)

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
    """Return the raw spec definitions list (for facet endpoints)."""
    return _RAW_DEFS
