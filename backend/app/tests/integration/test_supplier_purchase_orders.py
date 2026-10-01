"""Supplier purchase orders, whatever the supplier (R4 / S4).

One purchase order per supplier of the paid order that orders automatically,
delivered to the main warehouse; Ingram keeps its historical switch.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.features.integrations.models.supplier import Supplier, SupplierKind
from app.features.integrations.models.supplier_order import (
    SupplierOrder,
    SupplierOrderStatus,
)
from app.features.integrations.services import supplier_order_service as svc
from app.features.order.models.order import Order
from app.features.order.models.order_line import OrderLine
from app.features.order.models.order_status import OrderStatus
from app.features.place.models import Place
from app.features.product.models.product import Product
from app.features.user.models.user import User
from app.services import suppliers as registry
from app.services.suppliers.base import (
    NormalizedPricing,
    NormalizedProductData,
    PurchaseOrderLine,
    PurchaseOrderResult,
    ShipTo,
    SupplierAdapter,
    SupplierHealth,
)


class OrderingAdapter(SupplierAdapter):
    adapter_key = "demo_orders"
    display_name = "Démo commandes"
    supports_purchase_orders = True
    placed: list[dict[str, Any]] = []
    fail: bool = False

    async def fetch_catalog(
        self, category: str, **filters: Any
    ) -> AsyncIterator[list[NormalizedProductData]]:
        del category, filters
        if False:
            yield []

    async def fetch_price_and_availability(
        self, skus: list[str]
    ) -> dict[str, NormalizedPricing]:
        return {}

    async def health_check(self) -> SupplierHealth:
        return SupplierHealth(healthy=True, configured=True, message="ok")

    async def create_purchase_order(
        self,
        *,
        customer_order_number: str,
        lines: list[PurchaseOrderLine],
        ship_to: ShipTo,
        notes: str | None = None,
    ) -> PurchaseOrderResult:
        if type(self).fail:
            raise RuntimeError("supplier down")
        type(self).placed.append(
            {
                "supplier": self.name,
                "number": customer_order_number,
                "lines": lines,
                "ship_to": ship_to,
            }
        )
        return PurchaseOrderResult(
            order_number=f"PO-{self.name}", status_label="accepted", raw={"ok": True}
        )


class NoOrderAdapter(OrderingAdapter):
    adapter_key = "demo_no_orders"
    supports_purchase_orders = False


@pytest.fixture(autouse=True)
def adapters(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(registry.ADAPTERS, OrderingAdapter.adapter_key, OrderingAdapter)
    monkeypatch.setitem(registry.ADAPTERS, NoOrderAdapter.adapter_key, NoOrderAdapter)
    OrderingAdapter.placed = []
    OrderingAdapter.fail = False
    registry._INSTANCES.clear()


async def _seed(session: AsyncSession, *, warehouse_address: bool = True) -> uuid.UUID:
    session.add(
        Place(
            name="Entrepôt principal",
            type="warehouse",
            code="MAIN",
            country="PF",
            is_main_warehouse=True,
            address_line1="1 rue du Port" if warehouse_address else None,
            city="Papeete" if warehouse_address else None,
            postal_code="98714",
        )
    )
    for code, key, auto in (
        ("alpha", OrderingAdapter.adapter_key, True),
        ("beta", OrderingAdapter.adapter_key, False),
        ("gamma", NoOrderAdapter.adapter_key, True),
    ):
        session.add(
            Supplier(
                code=code,
                name=code,
                kind=SupplierKind.API,
                adapter_key=key,
                auto_purchase_order=auto,
            )
        )
    buyer = User(email=f"b+{uuid.uuid4().hex[:6]}@t.local", hashed_password="x")
    status = OrderStatus(name="Paid")
    session.add_all([buyer, status])
    await session.flush()
    order = Order(
        user_id=buyer.id,
        order_status_id=status.id,
        order_number="CMD-1",
        total_amount=Decimal("100"),
    )
    session.add(order)
    await session.flush()
    for supplier, sku, qty in (
        ("alpha", "A-1", 2),
        ("alpha", "A-2", 1),
        ("beta", "B-1", 1),
        ("gamma", "G-1", 1),
        (None, None, 1),
    ):
        product = Product(
            name=f"P {sku}",
            supplier_name=supplier,
            supplier_sku=sku,
            supplier_price=Decimal("10"),
        )
        session.add(product)
        await session.flush()
        session.add(
            OrderLine(
                order_id=order.id,
                product_id=product.id,
                quantity=qty,
                unit_price=Decimal(20),
            )
        )
    order_id = order.id
    await session.commit()
    return order_id


async def _rows(session: AsyncSession) -> dict[str, SupplierOrder]:
    rows = (await session.exec(select(SupplierOrder))).all()
    return {r.supplier_name: r for r in rows}


@pytest.mark.asyncio
async def test_one_order_per_supplier_set_to_order(db_session: AsyncSession) -> None:
    order_id = await _seed(db_session)

    await svc.process_purchase_orders(db_session, order_id)

    (placed,) = OrderingAdapter.placed
    assert placed["supplier"] == "alpha"
    assert placed["number"] == str(order_id).replace("-", "")
    assert [(line.supplier_sku, line.quantity) for line in placed["lines"]] == [
        ("A-1", 2),
        ("A-2", 1),
    ]
    ship_to: ShipTo = placed["ship_to"]
    assert (ship_to.address_line1, ship_to.city, ship_to.country_code) == (
        "1 rue du Port",
        "Papeete",
        "PF",
    )
    rows = await _rows(db_session)
    # beta orders by hand; gamma's integration cannot order: neither row exists.
    assert set(rows) == {"alpha"}
    assert rows["alpha"].status == SupplierOrderStatus.SUBMITTED
    assert rows["alpha"].supplier_order_number == "PO-alpha"

    # Idempotent: a second capture does not order twice.
    await svc.process_purchase_orders(db_session, order_id)
    assert len(OrderingAdapter.placed) == 1


@pytest.mark.asyncio
async def test_manual_order_and_integration_without_orders(
    db_session: AsyncSession,
) -> None:
    order_id = await _seed(db_session)

    beta = await svc.process_supplier_purchase_order(db_session, order_id, "beta")
    assert beta.status == SupplierOrderStatus.SUBMITTED

    # Asked by hand (admin retry) for a supplier whose integration cannot order.
    gamma = await svc.process_supplier_purchase_order(
        db_session, order_id, "gamma", reraise_on_api_error=False
    )
    assert gamma.status == SupplierOrderStatus.ERROR
    assert "no integration" in (gamma.error_message or "")


@pytest.mark.asyncio
async def test_no_delivery_address_is_an_error(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "INGRAM_SHIP_TO_ADDRESS_LINE1", None)
    order_id = await _seed(db_session, warehouse_address=False)

    await svc.process_purchase_orders(db_session, order_id)

    rows = await _rows(db_session)
    assert rows["alpha"].status == SupplierOrderStatus.ERROR
    assert "entrepôt principal" in (rows["alpha"].error_message or "")
    assert OrderingAdapter.placed == []


@pytest.mark.asyncio
async def test_api_failure_is_recorded_then_reraised(
    db_session: AsyncSession,
) -> None:
    order_id = await _seed(db_session)
    OrderingAdapter.fail = True

    with pytest.raises(RuntimeError):
        await svc.process_purchase_orders(db_session, order_id)
    rows = await _rows(db_session)
    assert rows["alpha"].status == SupplierOrderStatus.ERROR
    assert rows["alpha"].attempts == 1

    OrderingAdapter.fail = False
    record = await svc.process_supplier_purchase_order(
        db_session, order_id, "alpha", reraise_on_api_error=False
    )
    assert record.status == SupplierOrderStatus.SUBMITTED
    assert record.attempts == 2


def test_ingram_keeps_its_environment_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ingram = Supplier(
        code="ingram_micro",
        name="Ingram",
        kind=SupplierKind.API,
        adapter_key="ingram_micro",
    )
    monkeypatch.setattr(settings, "INGRAM_ORDER_CREATION_ENABLED", False)
    assert svc.orders_automatically(ingram) is False
    monkeypatch.setattr(settings, "INGRAM_ORDER_CREATION_ENABLED", True)
    assert svc.orders_automatically(ingram) is True
    ingram.is_active = False
    assert svc.orders_automatically(ingram) is False
