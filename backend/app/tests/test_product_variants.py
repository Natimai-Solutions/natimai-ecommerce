"""Unit: variant naming, option axes and the parent availability SQL."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import postgresql
from sqlmodel import col, select

import app.features.models  # noqa: F401 — mapper registry
from app.api.routes.cart import _get_active_product_or_404
from app.core.errors import AppError
from app.features.inventory.services.availability import available_quantity_expression
from app.features.product.models.product import Product
from app.features.product.services.variants import option_axes, variant_display_name


def test_display_name_joins_the_option_values() -> None:
    assert variant_display_name("T-shirt", {"Taille": "M", "Couleur": "Noir"}) == (
        "T-shirt — M / Noir"
    )
    assert variant_display_name("T-shirt", {}) == "T-shirt"
    assert variant_display_name("T-shirt", None) == "T-shirt"


def test_axes_keep_first_seen_order_across_variants() -> None:
    variants = [
        SimpleNamespace(variant_options={"Taille": "M"}),
        SimpleNamespace(variant_options={"Couleur": "Noir", "Taille": "L"}),
        SimpleNamespace(variant_options=None),
    ]
    assert option_axes(variants) == ["Taille", "Couleur"]


def test_parent_availability_sums_its_active_variants() -> None:
    stmt = select(col(Product.id)).where(available_quantity_expression() > 0)
    sql = str(
        stmt.compile(
            dialect=postgresql.dialect(),  # type: ignore[no-untyped-call]
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "FROM products AS variant" in sql
    assert "variant.parent_product_id = products.id" in sql
    assert "variant.is_active IS true" in sql


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_a_parent_with_variants_is_not_sellable_as_such() -> None:
    parent = SimpleNamespace(
        id=uuid.uuid4(), is_active=True, is_admin_active=True, has_variants=True
    )
    session = AsyncMock()
    session.get = AsyncMock(return_value=parent)
    with pytest.raises(AppError) as raised:
        await _get_active_product_or_404(cast(Any, session), product_id=parent.id)
    assert raised.value.code == "cart.product.has_variants"
    assert raised.value.status_code == 409
