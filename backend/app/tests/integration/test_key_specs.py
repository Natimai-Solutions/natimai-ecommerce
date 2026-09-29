"""Integration: key-spec tiles computed from projected specs on real Postgres.

Covers the YAML fallback (no definition rows yet), the admin override through
``spec_definitions.highlight_rank``, and a product that has none of the
highlighted specs.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.product.models.product import PricingMode, Product
from app.features.product.models.spec_definition import SpecDefinition
from app.features.product.services.key_specs import compute_key_specs
from app.features.product.services.spec_projection import (
    get_spec_definitions,
    upsert_product_specs,
)

_LAPTOP_SPECS = [
    {"name": "Famille de processeur", "value": "Intel Core Ultra 5"},
    {"name": "Mémoire installée", "value": "16 Go"},
    {"name": "Capacité du SSD", "value": "512 Go"},
    {"name": "Taille de l'écran", "value": '14"'},
    {"name": "Système d'exploitation", "value": "Windows 11 Pro"},
]


def _laptop(**overrides: object) -> Product:
    product = Product(
        name="ThinkPad E14 Gen 6",
        supplier_name="tahiti",
        supplier_sku="tahiti-e14",
        supplier_category="Ordinateur portable",
        pricing_mode=PricingMode.FIXED,
        base_price=Decimal("149900"),
        supplier_quantity=Decimal("12"),
        manufacturer="Lenovo",
        is_enriched=True,
        technical_specifications=_LAPTOP_SPECS,
    )
    for field, value in overrides.items():
        setattr(product, field, value)
    return product


async def _persist_with_specs(db_session: AsyncSession, product: Product) -> Product:
    db_session.add(product)
    await db_session.flush()
    await upsert_product_specs(db_session, product)
    await db_session.flush()
    return product


@pytest.mark.asyncio
async def test_tiles_follow_the_yaml_ranks(db_session: AsyncSession) -> None:
    product = await _persist_with_specs(db_session, _laptop())

    tiles = await compute_key_specs(db_session, product)

    assert [(t.label, t.value) for t in tiles] == [
        ("Famille de processeur", "Intel Core Ultra 5"),
        ("Mémoire RAM", "16 Go"),
        ("Stockage", "512 Go"),
        ("Taille d'écran", "14 pouces"),
    ]


@pytest.mark.asyncio
async def test_admin_ranks_override_the_yaml(db_session: AsyncSession) -> None:
    # Definitions seeded in the DB (as the migration does), then re-ranked:
    # the screen first, the processor no longer highlighted.
    ranks = {"screen_inches": 1, "memory_gb": 2, "cpu_family": None}
    for spec in get_spec_definitions():
        db_session.add(
            SpecDefinition(
                key=spec["key"],
                label_fr=spec["label_fr"],
                type=spec["type"],
                unit=spec.get("unit"),
                categories=spec["categories"],
                aliases=spec["aliases"],
                highlight_rank=ranks.get(spec["key"], spec.get("highlight_rank")),
            )
        )
    product = await _persist_with_specs(db_session, _laptop())

    tiles = await compute_key_specs(db_session, product)

    assert [t.key for t in tiles] == ["screen_inches", "memory_gb", "storage_gb"]


@pytest.mark.asyncio
async def test_no_tiles_without_highlighted_values(db_session: AsyncSession) -> None:
    product = await _persist_with_specs(
        db_session,
        _laptop(
            supplier_sku="tahiti-cable",
            name="Câble HDMI 2 m",
            supplier_category="Câbles",
            technical_specifications=[{"name": "Longueur du câble", "value": "2 m"}],
        ),
    )

    assert await compute_key_specs(db_session, product) == []
