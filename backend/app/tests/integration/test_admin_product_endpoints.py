"""Integration tests: admin product create/edit endpoints.

- ``POST /admin/products`` forces ``is_supplier_managed=False`` (manual product).
- ``PUT /admin/products/{id}`` records every edited field in ``overridden_fields``
  so a later supplier sync will not overwrite the admin's values.
"""

from decimal import Decimal

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.admin_product import admin_create_product, admin_update_product
from app.features.product.models.product import Product, ProductCreate, ProductUpdate
from app.features.user.models.user import User


async def _seed_admin(session: AsyncSession) -> User:
    admin = User(
        email="admin@test.local",
        is_active=True,
        is_superuser=True,
        hashed_password="x",
    )
    session.add(admin)
    await session.flush()
    return admin


@pytest.mark.asyncio
async def test_admin_create_forces_manual_product(db_session: AsyncSession) -> None:
    admin = await _seed_admin(db_session)
    # Even if the caller sends is_supplier_managed=True, it is forced to False.
    product = await admin_create_product(
        session=db_session,
        current_user=admin,
        payload=ProductCreate(name="Produit manuel", is_supplier_managed=True),
    )
    assert product.is_supplier_managed is False
    assert product.name == "Produit manuel"


@pytest.mark.asyncio
async def test_admin_update_records_overrides(db_session: AsyncSession) -> None:
    admin = await _seed_admin(db_session)
    supplier_product = Product(
        name="Nom fournisseur",
        base_price=Decimal("0.00"),
        is_supplier_managed=True,
        supplier_name="ingram_micro",
        supplier_sku="SKU-XYZ",
    )
    db_session.add(supplier_product)
    await db_session.flush()
    product_id = supplier_product.id

    await admin_update_product(
        session=db_session,
        current_user=admin,
        product_id=product_id,
        payload=ProductUpdate(name="Nom admin", base_price=Decimal("1500")),
    )

    refreshed = await db_session.get(Product, product_id)
    assert refreshed is not None
    assert refreshed.name == "Nom admin"
    # Both edited fields are locked; flags/bookkeeping are not treated as overrides.
    assert set(refreshed.overridden_fields or []) == {"name", "base_price"}


@pytest.mark.asyncio
async def test_admin_update_accumulates_overrides(db_session: AsyncSession) -> None:
    admin = await _seed_admin(db_session)
    product = Product(name="A", is_supplier_managed=True, overridden_fields=["name"])
    db_session.add(product)
    await db_session.flush()
    product_id = product.id

    await admin_update_product(
        session=db_session,
        current_user=admin,
        product_id=product_id,
        payload=ProductUpdate(description="Nouvelle description"),
    )

    refreshed = await db_session.get(Product, product_id)
    assert refreshed is not None
    assert set(refreshed.overridden_fields or []) == {"name", "description"}


@pytest.mark.asyncio
async def test_admin_gallery_is_cleaned_and_locked(db_session: AsyncSession) -> None:
    """Several images per product: the gallery is stored trimmed and
    deduplicated, locked against the supplier sync like the main image, and
    ``None`` / blank entries empty it."""
    from types import SimpleNamespace
    from typing import cast

    seeded = await _seed_admin(db_session)
    # The routes commit: a detached snapshot avoids lazy reloads of the user.
    admin = cast(User, SimpleNamespace(id=seeded.id, is_superuser=True))
    created = await admin_create_product(
        session=db_session,
        current_user=admin,
        payload=ProductCreate(
            name="Galerie",
            image_url="https://img.test/main.jpg",
            gallery_urls=[" https://img.test/a.jpg ", "", "https://img.test/a.jpg"],
        ),
    )
    assert created.gallery_urls == ["https://img.test/a.jpg"]

    updated = await admin_update_product(
        session=db_session,
        current_user=admin,
        product_id=created.id,
        payload=ProductUpdate(
            gallery_urls=["https://img.test/b.jpg", "https://img.test/c.jpg"]
        ),
    )
    assert updated.gallery_urls == ["https://img.test/b.jpg", "https://img.test/c.jpg"]
    assert "gallery_urls" in (updated.overridden_fields or [])

    emptied = await admin_update_product(
        session=db_session,
        current_user=admin,
        product_id=created.id,
        payload=ProductUpdate(gallery_urls=None),
    )
    assert emptied.gallery_urls == []
