"""Cost price and margin, on products and on orders (real database).

A fixed-price article with its purchase cost shows its margin; an imported
one counts customs in its cost price; the admin list sorts by margin; the
product form previews the margin of unsaved values; an order shows the margin
of its lines from the cost frozen at checkout. Storefront visitors never
receive any of these figures.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, cast

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.admin_orders import get_order_detail
from app.api.routes.admin_product import (
    MarginPreviewRequest,
    admin_create_product,
    admin_update_product,
    preview_margin,
)
from app.api.routes.cart import _unit_cost_snapshot
from app.api.routes.product import router as product_router
from app.core.config import settings
from app.core.field_visibility import reveal_internal_fields
from app.features.order.models.order import Order
from app.features.order.models.order_line import OrderLine, OrderLinePublic
from app.features.order.models.order_status import OrderStatus
from app.features.product.models.currency_rate import CurrencyRate, CurrencyRateSource
from app.features.product.models.product import (
    PricingMode,
    Product,
    ProductCreate,
    ProductPublic,
    ProductUpdate,
)
from app.features.product.models.tax_rate import TaxRate
from app.features.product.services.margin import compute_margin
from app.features.user.models.user import User

TODAY = date.today()


async def _admin(session: AsyncSession) -> User:
    admin = User(
        email=f"admin+{uuid.uuid4().hex[:6]}@t.local",
        is_active=True,
        is_superuser=True,
        hashed_password="x",
    )
    session.add(admin)
    await session.flush()
    return admin


async def _vat(session: AsyncSession, pct: str = "16") -> uuid.UUID:
    rate = TaxRate(
        code=f"VAT_{pct}",
        label=f"TVA {pct} %",
        rate_pct=Decimal(pct),
        territory_code=settings.TAX_TERRITORY_CODE,
        valid_from=TODAY - timedelta(days=1),
        is_active=True,
        is_admin_active=True,
    )
    session.add(rate)
    await session.flush()
    return rate.id


def test_margin_figures() -> None:
    figures = compute_margin(
        price_incl_tax=Decimal("11600"),
        tax_rate_pct=Decimal("16"),
        unit_cost=Decimal("6000"),
    )
    assert figures is not None
    assert figures.price_excl_tax == Decimal("10000.00")
    assert figures.tax_amount == Decimal("1600.00")
    assert figures.margin_amount == Decimal("4000.00")
    assert figures.margin_pct == Decimal("40.00")  # taux de marque
    assert figures.markup_pct == Decimal("66.67")  # taux de marge
    # A payment commission is a cost of the sale.
    with_fee = compute_margin(
        price_incl_tax=Decimal("11600"),
        tax_rate_pct=Decimal("16"),
        unit_cost=Decimal("6000"),
        commission_pct=Decimal("2"),
    )
    assert with_fee is not None and with_fee.margin_amount == Decimal("3768.00")
    assert (
        compute_margin(price_incl_tax=Decimal("100"), tax_rate_pct=None, unit_cost=None)
        is None
    )


@pytest.mark.asyncio
async def test_a_fixed_price_article_with_its_cost_shows_its_margin(
    db_session: AsyncSession,
) -> None:
    admin = await _admin(db_session)
    vat = await _vat(db_session)
    created = await admin_create_product(
        session=db_session,
        current_user=admin,
        payload=ProductCreate(
            name="Casque audio",
            pricing_mode=PricingMode.FIXED,
            base_price=Decimal("11600"),
            cost_amount=Decimal("6000"),
            cost_currency=settings.REFERENCE_CURRENCY,
            tax_rate_id=vat,
        ),
    )
    assert created.unit_cost_cached == Decimal("6000.00")
    assert created.margin_cached == Decimal("4000.00")
    assert created.margin_pct_cached == Decimal("40.00")
    product_id = created.id

    # A new price updates the margin in the same write.
    await db_session.refresh(admin)
    await admin_update_product(
        session=db_session,
        current_user=admin,
        product_id=product_id,
        payload=ProductUpdate(base_price=Decimal("8120")),
    )
    product = await db_session.get(Product, product_id)
    assert product is not None
    assert product.margin_cached == Decimal("1000.00")  # 7000 HT − 6000


@pytest.mark.asyncio
async def test_an_imported_article_counts_customs_in_its_cost(
    db_session: AsyncSession,
) -> None:
    admin = await _admin(db_session)
    vat = await _vat(db_session)
    db_session.add(
        CurrencyRate(
            currency_code="EUR",
            rate_to_reference=Decimal("119.332"),
            valid_from=TODAY - timedelta(days=1),
            source=CurrencyRateSource.manual,
            is_active=True,
            is_admin_active=True,
        )
    )
    await db_session.flush()
    created = await admin_create_product(
        session=db_session,
        current_user=admin,
        payload=ProductCreate(
            name="Écran importé",
            pricing_mode=PricingMode.IMPORT,
            cost_amount=Decimal("100"),
            cost_currency="EUR",
            customs_rate_pct=Decimal("10"),
            margin_rate_pct=Decimal("25"),
            tax_rate_id=vat,
        ),
    )
    # 100 € → 11 933,20 F, + 10 % de douane (assurance 0 %).
    assert created.unit_cost_cached == Decimal("13126.52")
    assert created.margin_cached is not None
    assert created.margin_cached > 0


@pytest.mark.asyncio
async def test_the_form_previews_unsaved_values(db_session: AsyncSession) -> None:
    admin = await _admin(db_session)
    vat = await _vat(db_session)
    await db_session.commit()
    preview = await preview_margin(
        MarginPreviewRequest(
            pricing_mode=PricingMode.FIXED,
            base_price=Decimal("5800"),
            cost_amount=Decimal("6000"),
            tax_rate_id=vat,
        ),
        cast(Any, db_session),
        cast(Any, admin),
    )
    assert preview.price_excl_tax == Decimal("5000.00")
    assert preview.margin_amount == Decimal("-1000.00")
    assert preview.note is not None and "perte" in preview.note

    no_cost = await preview_margin(
        MarginPreviewRequest(
            pricing_mode=PricingMode.DOMESTIC,
            cost_amount=Decimal("0"),
            margin_rate_pct=Decimal("30"),
            tax_rate_id=vat,
        ),
        cast(Any, db_session),
        cast(Any, admin),
    )
    assert no_cost.margin_amount is None
    assert no_cost.note is not None and "coût" in no_cost.note


@pytest.mark.asyncio
async def test_the_admin_list_sorts_by_margin(db_session: AsyncSession) -> None:
    admin = await _admin(db_session)
    vat = await _vat(db_session)
    for name, price, cost in (
        ("Petite marge", "1160", "900"),
        ("Grosse marge", "11600", "1000"),
        ("Sans coût", "2320", "0"),
    ):
        await admin_create_product(
            session=db_session,
            current_user=admin,
            payload=ProductCreate(
                name=name,
                pricing_mode=PricingMode.FIXED,
                base_price=Decimal(price),
                cost_amount=Decimal(cost),
                tax_rate_id=vat,
            ),
        )
        await db_session.refresh(admin)

    read_multi = next(
        route.endpoint
        for route in product_router.routes
        if getattr(route, "name", "") == "get_multiple_products"
    )
    listing = await read_multi(
        session=db_session,
        skip=0,
        limit=10,
        order_by=None,
        include_archived=True,
        status=None,
        search=None,
        sort="margin_desc",
        current_user=admin,
    )
    assert [p.name for p in listing.data] == [
        "Grosse marge",
        "Petite marge",
        "Sans coût",
    ]


@pytest.mark.asyncio
async def test_an_order_shows_the_margin_of_its_lines(
    db_session: AsyncSession,
) -> None:
    admin = await _admin(db_session)
    vat = await _vat(db_session)
    status = OrderStatus(name="Paid")
    db_session.add(status)
    await db_session.flush()
    product = Product(
        name="Clavier",
        pricing_mode=PricingMode.FIXED,
        base_price=Decimal("5800"),
        cost_amount=Decimal("3000"),
        cost_currency=settings.REFERENCE_CURRENCY,
        tax_rate_id=vat,
    )
    other = Product(name="Tapis de souris", base_price=Decimal("1160"))
    db_session.add_all([product, other])
    await db_session.flush()
    order = Order(
        user_id=admin.id,
        order_status_id=status.id,
        order_number="CMD-TEST-1",
        currency=settings.REFERENCE_CURRENCY,
        subtotal_amount=Decimal("12760"),
        total_amount=Decimal("12760"),
    )
    db_session.add(order)
    await db_session.flush()
    snapshot = await _unit_cost_snapshot(cast(Any, db_session), product)
    assert snapshot == Decimal("3000.00")
    db_session.add_all(
        [
            OrderLine(
                order_id=order.id,
                product_id=product.id,
                quantity=2,
                unit_price=Decimal("5800"),
                tax_rate_id=vat,
                unit_cost_snapshot=snapshot,
            ),
            # A line whose cost was never known.
            OrderLine(
                order_id=order.id,
                product_id=other.id,
                quantity=1,
                unit_price=Decimal("1160"),
                tax_rate_id=vat,
            ),
        ]
    )
    order_id = order.id
    await db_session.commit()

    detail = await get_order_detail(order_id, cast(Any, db_session), admin)
    lines = {line.product_name: line for line in detail.lines}
    keyboard = lines["Clavier"]
    assert keyboard.line_total_excl_tax == 10000.0
    assert keyboard.line_cost == 6000.0
    assert keyboard.line_margin == 4000.0
    assert keyboard.margin_pct == 40.0
    assert lines["Tapis de souris"].line_margin is None
    assert detail.margin is not None
    assert detail.margin.margin == 4000.0
    assert detail.margin.complete is False
    assert detail.margin.lines_without_cost == 1


def test_storefront_payloads_never_carry_costs() -> None:
    product = ProductPublic.model_validate(
        {
            "id": uuid.uuid4(),
            "name": "Article",
            "base_price": Decimal("1000"),
            "cost_amount": Decimal("600"),
            "supplier_price": Decimal("550"),
            "margin_cached": Decimal("262"),
            "is_active": True,
        }
    )
    public = json.loads(product.model_dump_json())
    assert "cost_amount" not in public
    assert "supplier_price" not in public
    assert "margin_cached" not in public
    assert public["base_price"] == "1000"

    line = OrderLinePublic.model_validate(
        {
            "id": uuid.uuid4(),
            "order_id": uuid.uuid4(),
            "product_id": uuid.uuid4(),
            "quantity": 1,
            "unit_price": Decimal("1000"),
            "cost_amount_snapshot": Decimal("600"),
            "unit_cost_snapshot": Decimal("600"),
            "is_active": True,
        }
    )
    assert "unit_cost_snapshot" not in line.model_dump()


def test_a_superuser_request_receives_them() -> None:
    import contextvars

    def admin_request() -> dict[str, Any]:
        reveal_internal_fields()
        return ProductPublic.model_validate(
            {
                "id": uuid.uuid4(),
                "name": "Article",
                "cost_amount": Decimal("600"),
                "is_active": True,
            }
        ).model_dump()

    # Each request runs in its own context: revealing does not leak out.
    revealed = contextvars.copy_context().run(admin_request)
    assert revealed["cost_amount"] == Decimal("600")
    after = ProductPublic.model_validate(
        {
            "id": uuid.uuid4(),
            "name": "A",
            "cost_amount": Decimal("1"),
            "is_active": True,
        }
    ).model_dump()
    assert "cost_amount" not in after
