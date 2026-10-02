"""Related products (R9 / T7): manual links, category suggestions, cart."""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import cast

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.admin_categories import AdminCategoryUpdate, update_category
from app.api.routes.admin_product import (
    admin_list_product_links,
    admin_set_product_links,
)
from app.api.routes.product_catalog import (
    RelatedToRequest,
    get_related_products,
    get_related_to_products,
)
from app.core.errors import AppError
from app.features.order.models.order import Order
from app.features.order.models.order_line import OrderLine
from app.features.order.models.order_status import OrderStatus
from app.features.product.models.category import Category
from app.features.product.models.product import PricingMode, Product
from app.features.product.models.product_link import ProductLinkWrite
from app.features.user.models.user import User


def _product(name: str, category_id: uuid.UUID, *, qty: str = "5") -> Product:
    return Product(
        name=name,
        pricing_mode=PricingMode.FIXED,
        base_price=Decimal("1000"),
        supplier_name="tahiti",
        supplier_sku=f"tahiti-{name}",
        supplier_quantity=Decimal(qty),
        category_id=category_id,
        is_enriched=True,
        is_supplier_managed=True,
    )


@pytest.mark.asyncio
async def test_links_and_category_rules_feed_the_storefront_block(
    db_session: AsyncSession,
) -> None:
    admin_row = User(
        email=f"admin+{uuid.uuid4().hex[:6]}@test.local",
        is_superuser=True,
        is_active=True,
        hashed_password="x",
    )
    db_session.add(admin_row)
    await db_session.flush()
    admin = cast(User, SimpleNamespace(id=admin_row.id, is_superuser=True))
    pcs = Category(name="PC fixes")
    screens = Category(name="Écrans")
    keyboards = Category(name="Claviers")
    db_session.add_all([pcs, screens, keyboards])
    await db_session.flush()

    pc = _product("PC fixe", pcs.id)
    other_pc = _product("Autre PC", pcs.id)
    screen_a = _product("Écran A", screens.id)
    screen_b = _product("Écran B (best seller)", screens.id)
    screen_out = _product("Écran épuisé", screens.id, qty="0")
    keyboard = _product("Clavier", keyboards.id)
    db_session.add_all([pc, other_pc, screen_a, screen_b, screen_out, keyboard])
    await db_session.flush()
    ids = {
        p.name: p.id for p in (pc, other_pc, screen_a, screen_b, screen_out, keyboard)
    }
    pc_id, pcs_id = pc.id, pcs.id
    screens_id, keyboards_id = screens.id, keyboards.id

    # Two sales of screen B: it ranks first among the suggested category.
    buyer = User(
        email=f"buyer+{uuid.uuid4().hex[:6]}@test.local",
        is_active=True,
        hashed_password="x",
    )
    status = OrderStatus(name=f"Pending-{uuid.uuid4().hex[:4]}")
    db_session.add_all([buyer, status])
    await db_session.flush()
    order = Order(
        user_id=buyer.id,
        order_status_id=status.id,
        total_amount=Decimal("0"),
        subtotal_amount=Decimal("0"),
        shipping_fee_amount=Decimal("0"),
        payment_fee_amount=Decimal("0"),
        total_fees_amount=Decimal("0"),
    )
    db_session.add(order)
    await db_session.flush()
    db_session.add(
        OrderLine(
            order_id=order.id,
            product_id=screen_b.id,
            quantity=2,
            unit_price=Decimal("1"),
        )
    )
    await db_session.commit()

    # Manual links on the PC: the keyboard as accessory, the other PC as alternative.
    with pytest.raises(AppError) as self_link:
        await admin_set_product_links(
            db_session, admin, pc_id, [ProductLinkWrite(linked_product_id=pc_id)]
        )
    assert self_link.value.code == "product.links.invalid"
    links = await admin_set_product_links(
        db_session,
        admin,
        pc_id,
        [
            ProductLinkWrite(
                linked_product_id=ids["Clavier"], kind="accessory", position=0
            ),
            ProductLinkWrite(
                linked_product_id=ids["Autre PC"], kind="alternative", position=0
            ),
        ],
    )
    assert [(link.name, link.kind) for link in links] == [
        ("Clavier", "accessory"),
        ("Autre PC", "alternative"),
    ]
    assert [
        link.name for link in await admin_list_product_links(db_session, admin, pc_id)
    ] == [
        "Clavier",
        "Autre PC",
    ]

    # Category rule: from PC fixes, suggest Écrans (then Claviers).
    item = await update_category(
        pcs_id,
        AdminCategoryUpdate(suggested_category_ids=[screens_id, keyboards_id]),
        db_session,
        admin,
    )
    assert item.suggested_category_ids == [screens_id, keyboards_id]

    related = await get_related_products(pc_id, db_session, limit=8, current_user=None)
    # Manual accessory first, then the suggested categories' best sellers,
    # never the out-of-stock screen nor a duplicate of the manual link.
    assert [p.name for p in related.accessories] == [
        "Clavier",
        "Écran B (best seller)",
        "Écran A",
    ]
    assert [p.name for p in related.alternatives] == ["Autre PC"]

    # The cart: suggestions for its products, the cart itself excluded.
    cart = await get_related_to_products(
        RelatedToRequest(product_ids=[pc_id, ids["Clavier"]]), db_session, None
    )
    assert [p.name for p in cart.accessories] == ["Écran B (best seller)", "Écran A"]
    assert cart.alternatives == []
