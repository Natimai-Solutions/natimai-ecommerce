"""Integration tests (real DB): import en brouillon — a supplier set to
« nouveaux articles en brouillon » creates hidden products the admin
publishes, one by one or in bulk."""

from __future__ import annotations

import io
import uuid
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import UploadFile
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.admin_product import PublishRequest, admin_publish_products
from app.api.routes.admin_suppliers import create_supplier, update_supplier
from app.api.routes.suppliers import import_catalog_file
from app.features.integrations.models.supplier import (
    Supplier,
    SupplierCreate,
    SupplierKind,
    SupplierUpdate,
)
from app.features.product.crud.product import crud_product
from app.features.product.models.product import Product
from app.features.product.services.publication import (
    DRAFT,
    publication_blockers,
    publication_conditions,
)
from app.features.user.models.user import User


@pytest.mark.asyncio
async def test_new_products_wait_for_the_admin_when_the_supplier_says_so(
    db_session: AsyncSession,
) -> None:
    admin = User(
        email=f"admin+{uuid.uuid4().hex[:6]}@test.local",
        is_active=True,
        is_superuser=True,
        hashed_password="x",
    )
    db_session.add(admin)
    await db_session.flush()
    admin_view = cast(User, SimpleNamespace(id=admin.id))
    await db_session.commit()

    code = f"local_{uuid.uuid4().hex[:6]}"
    mapping = {
        "supplier_sku": "Ref",
        "name": "Nom",
        "price": "Prix",
        "quantity": "Stock",
    }
    await create_supplier(
        payload=SupplierCreate(
            code=code,
            name="Distributeur local",
            kind=SupplierKind.FILE,
            is_domestic=True,
            price_currency="XPF",
            column_mapping=mapping,
            import_as_draft=True,
        ),
        session=db_session,
        current_user=admin_view,
    )
    supplier = (
        await db_session.exec(select(Supplier).where(Supplier.code == code))
    ).first()
    assert supplier is not None and supplier.import_as_draft is True

    def upload(content: str) -> UploadFile:
        return UploadFile(file=io.BytesIO(content.encode()), filename="cat.csv")

    response = await import_catalog_file(
        supplier=supplier,
        session=db_session,
        current_user=admin_view,
        file=upload("Ref;Nom;Prix;Stock\nD-1;Clavier;4500;3\nD-2;Souris;1500;5\n"),
        mapping=None,
        dry_run=False,
    )
    assert response.statistics["new_products"] == 2

    rows = {
        p.supplier_sku: p
        for p in (
            await db_session.exec(select(Product).where(Product.supplier_name == code))
        ).all()
    }
    assert {sku: p.is_draft for sku, p in rows.items()} == {"D-1": True, "D-2": True}
    keyboard_id, mouse_id = rows["D-1"].id, rows["D-2"].id
    # Drafts are off the storefront and the cart guard names the reason.
    shown = (
        await db_session.exec(
            select(Product.id).where(
                Product.supplier_name == code, *publication_conditions()
            )
        )
    ).all()
    assert shown == []
    assert await publication_blockers(db_session, rows["D-1"]) == [DRAFT]

    # A later import updates the drafts without publishing them.
    supplier = (
        await db_session.exec(select(Supplier).where(Supplier.code == code))
    ).first()
    assert supplier is not None
    await import_catalog_file(
        supplier=supplier,
        session=db_session,
        current_user=admin_view,
        file=upload("Ref;Nom;Prix;Stock\nD-1;Clavier v2;4600;3\n"),
        mapping=None,
        dry_run=False,
    )
    keyboard = await db_session.get(Product, keyboard_id)
    assert keyboard is not None and keyboard.name == "Clavier v2" and keyboard.is_draft

    # The admin publishes: unknown ids are reported, published ones counted once.
    ghost = uuid.uuid4()
    published = await admin_publish_products(
        db_session,
        admin_view,
        PublishRequest(product_ids=[keyboard_id, keyboard_id, ghost]),
    )
    assert published.published == 1 and published.missing == [ghost]
    again = await admin_publish_products(
        db_session, admin_view, PublishRequest(product_ids=[keyboard_id, mouse_id])
    )
    assert again.published == 1 and again.already_published == 1
    shown = (
        await db_session.exec(
            select(Product.id).where(
                Product.supplier_name == code, *publication_conditions()
            )
        )
    ).all()
    assert set(shown) == {keyboard_id, mouse_id}

    # Once the supplier is switched back, a new reference is published at once.
    await update_supplier(
        code, SupplierUpdate(import_as_draft=False), db_session, admin_view
    )
    supplier = (
        await db_session.exec(select(Supplier).where(Supplier.code == code))
    ).first()
    assert supplier is not None
    await import_catalog_file(
        supplier=supplier,
        session=db_session,
        current_user=admin_view,
        file=upload("Ref;Nom;Prix;Stock\nD-3;Écran;25000;1\n"),
        mapping=None,
        dry_run=False,
    )
    screen = await crud_product.get_by_supplier_sku(
        session=db_session, supplier_sku="D-3", supplier_name=code
    )
    assert screen is not None and screen.is_draft is False
