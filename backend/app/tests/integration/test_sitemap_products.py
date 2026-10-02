"""R8 / U6 — ``GET /product/sitemap`` lists what the storefront shows, no more."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.product_catalog import sitemap_products
from app.features.product.models.product import PricingMode, Product

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _product(name: str, **overrides: object) -> Product:
    values: dict[str, object] = {
        "name": name,
        "description": "article de test",
        "pricing_mode": PricingMode.FIXED,
        "base_price": Decimal("10000"),
        "supplier_quantity": Decimal("3"),
        "is_enriched": True,
    }
    values.update(overrides)
    return Product(**values)  # type: ignore[arg-type]


async def test_sitemap_lists_only_storefront_products(db_session: AsyncSession) -> None:
    shown = _product("Clavier sitemap")
    hidden_draft = _product("Brouillon sitemap", is_draft=True)
    hidden_inactive = _product("Inactif sitemap", is_admin_active=False)
    hidden_free = _product("Gratuit sitemap", base_price=Decimal("0"))
    db_session.add_all([shown, hidden_draft, hidden_inactive, hidden_free])
    await db_session.flush()
    variant = _product("Déclinaison sitemap", parent_product_id=shown.id)
    shown_id = shown.id  # before the commit expires the instance
    db_session.add(variant)
    await db_session.commit()

    response = await sitemap_products(db_session)
    names = {item.name for item in response.items}
    assert "Clavier sitemap" in names
    assert names.isdisjoint(
        {
            "Brouillon sitemap",
            "Inactif sitemap",
            "Gratuit sitemap",
            "Déclinaison sitemap",
        }
    )
    entry = next(item for item in response.items if item.id == shown_id)
    assert entry.name == "Clavier sitemap"
