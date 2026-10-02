"""Integration tests (real DB): « me prévenir » — subscribing from the
product page (signed in or by e-mail), the orderability rule, the hourly
pass that e-mails once the product is back, listing and cancelling."""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import Request
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.stock_alerts import (
    cancel_my_stock_alert,
    list_my_stock_alerts,
    subscribe_stock_alert,
)
from app.core.errors import AppError
from app.features.notification.providers import NotificationResult
from app.features.product.models.product import Product
from app.features.product.models.stock_alert import StockAlertSubscribe
from app.features.product.services import stock_alert as service
from app.features.product.services.stock_alert import (
    notify_due_alerts,
    product_orderable,
)
from app.features.user.models.user import User


def _request() -> Request:
    """Un stub de requête : la route n'en lit que l'IP et l'en-tête captcha."""
    return cast(
        Request, SimpleNamespace(headers={}, client=SimpleNamespace(host="10.0.0.1"))
    )


def test_orderability_mirrors_the_storefront_rule() -> None:
    assert not product_orderable(SimpleNamespace(supplier_quantity=0))
    assert product_orderable(SimpleNamespace(supplier_quantity=Decimal("2")))
    assert product_orderable(
        SimpleNamespace(supplier_quantity=0, availability_mode="continuous")
    )
    assert not product_orderable(
        SimpleNamespace(supplier_quantity=0, availability_mode="on_demand")
    )
    assert product_orderable(
        SimpleNamespace(supplier_quantity=1, availability_mode="on_demand")
    )
    assert not product_orderable(
        SimpleNamespace(supplier_quantity=0, availability_mode="lot")
    )


@pytest.mark.asyncio
async def test_alerts_are_sent_once_when_the_product_is_back(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    buyer = User(
        email=f"buyer+{uuid.uuid4().hex[:8]}@test.local",
        is_active=True,
        hashed_password="x",
    )
    product = Product(name="Clavier", supplier_quantity=Decimal("0"))
    available = Product(name="Souris", supplier_quantity=Decimal("3"))
    db_session.add_all([buyer, product, available])
    await db_session.flush()
    buyer_email = buyer.email
    buyer_view = cast(User, SimpleNamespace(id=buyer.id, email=buyer_email))
    product_id, available_id = product.id, available.id
    await db_session.commit()

    sent: list[Any] = []

    class _Provider:
        async def send(self, message: Any) -> NotificationResult:
            sent.append(message)
            return NotificationResult(provider_code="fake", delivered=True)

    monkeypatch.setattr(service, "get_notification_provider", lambda _c: _Provider())

    # An available product refuses the alert; an unavailable one takes it,
    # once per e-mail (the account's when signed in, a typed one otherwise).
    with pytest.raises(AppError) as refused:
        await subscribe_stock_alert(
            StockAlertSubscribe(product_id=available_id),
            _request(),
            db_session,
            buyer_view,
        )
    assert refused.value.code == "stock_alert.orderable"
    first = await subscribe_stock_alert(
        StockAlertSubscribe(product_id=product_id), _request(), db_session, buyer_view
    )
    again = await subscribe_stock_alert(
        StockAlertSubscribe(product_id=product_id), _request(), db_session, buyer_view
    )
    assert first.id == again.id and first.email == buyer_email
    assert first.product_name == "Clavier"
    guest = await subscribe_stock_alert(
        StockAlertSubscribe(product_id=product_id, email="Visiteur@Example.PF"),
        _request(),
        db_session,
        None,
    )
    assert guest.user_id is None and guest.email == "visiteur@example.pf"
    with pytest.raises(AppError) as no_email:
        await subscribe_stock_alert(
            StockAlertSubscribe(product_id=product_id), _request(), db_session, None
        )
    assert no_email.value.code == "stock_alert.email_required"

    # Still out of stock: the pass sends nothing.
    assert await notify_due_alerts(db_session) == {"sent": 0, "failed": 0}

    # Back in stock: both alerts go out, exactly once.
    back = await db_session.get(Product, product_id)
    assert back is not None
    back.supplier_quantity = Decimal("5")
    db_session.add(back)
    await db_session.commit()
    assert await notify_due_alerts(db_session) == {"sent": 2, "failed": 0}
    assert {m.recipient for m in sent} == {buyer_email, "visiteur@example.pf"}
    assert "Clavier" in sent[0].subject and f"/produit/{product_id}" in sent[0].text
    assert await notify_due_alerts(db_session) == {"sent": 0, "failed": 0}

    # The customer sees the sent alert; a fresh pending one can be cancelled.
    mine = await list_my_stock_alerts(db_session, buyer_view)
    assert [(a.status, a.product_name) for a in mine] == [("sent", "Clavier")]
    gone = await db_session.get(Product, product_id)
    assert gone is not None
    gone.supplier_quantity = Decimal("0")
    db_session.add(gone)
    await db_session.commit()
    pending = await subscribe_stock_alert(
        StockAlertSubscribe(product_id=product_id), _request(), db_session, buyer_view
    )
    await cancel_my_stock_alert(pending.id, db_session, buyer_view)
    assert {a.status for a in await list_my_stock_alerts(db_session, buyer_view)} == {
        "sent"
    }
    with pytest.raises(AppError):
        await cancel_my_stock_alert(uuid.uuid4(), db_session, buyer_view)
