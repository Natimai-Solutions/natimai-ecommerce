"""PayPal through the generic provider pipeline (R3-P4 / P7), real database.

PayPal's API is replaced by an ``httpx.MockTransport``: the tests cover the
redirection, the server-side capture after the customer's approval, the
verified notifications (duplicates, contradictions, wrong amounts), the
deferred capture of an authorization and the refund in euros.
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.requests import Request

from app.api.routes.payments import confirm_my_payment, process_provider_webhook
from app.core.config import settings
from app.core.errors import AppError
from app.features.order.models.order import Order
from app.features.order.models.order_status import OrderStatus
from app.features.payment.models.payment import Payment
from app.features.payment.models.payment_status import PaymentStatus
from app.features.payment.models.payment_webhook_event import PaymentWebhookEvent
from app.features.payment.providers import paypal as paypal_module
from app.features.payment.providers.base import InitiationRequest
from app.features.payment.providers.paypal import PaypalProvider, charge_amount
from app.features.payment.services.capture_service import capture_payment
from app.features.payment.services.refund_service import refund_payment
from app.features.user.models.user import User
from app.handlers import payment as payment_handlers
from app.outbox.models import OutboxEvent

PAYPAL_ORDER = "5O190127TN364715T"
CAPTURE_ID = "3C679366HH908993F"
AUTHORIZATION_ID = "0VF52814937998046"


class FakePaypal:
    """PayPal's REST API, as much as the provider uses."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []
        self.signature_ok = True
        self.captured_value = "419.00"
        self.capture_issue: str | None = None
        self.payment_id = ""

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, path, body))
        if path == "/v2/checkout/orders":
            return httpx.Response(
                201,
                json={
                    "id": PAYPAL_ORDER,
                    "status": "PAYER_ACTION_REQUIRED",
                    "links": [
                        {
                            "rel": "payer-action",
                            "href": f"https://www.sandbox.paypal.com/checkoutnow?token={PAYPAL_ORDER}",
                        }
                    ],
                },
            )
        if path.endswith("/capture") and "/checkout/orders/" in path:
            if self.capture_issue:
                return httpx.Response(
                    422, json={"details": [{"issue": self.capture_issue}]}
                )
            return httpx.Response(201, json=self._order("captures"))
        if path.endswith("/authorize"):
            return httpx.Response(201, json=self._order("authorizations"))
        if path.startswith("/v2/payments/authorizations/"):
            return httpx.Response(201, json={"id": CAPTURE_ID, "status": "COMPLETED"})
        if path.startswith("/v2/payments/captures/"):
            return httpx.Response(201, json={"id": "REFUND1", "status": "COMPLETED"})
        if path == "/v1/notifications/verify-webhook-signature":
            status = "SUCCESS" if self.signature_ok else "FAILURE"
            return httpx.Response(200, json={"verification_status": status})
        return httpx.Response(404, json={})

    def _order(self, kind: str) -> dict[str, Any]:
        item = {
            "id": CAPTURE_ID if kind == "captures" else AUTHORIZATION_ID,
            "status": "COMPLETED" if kind == "captures" else "CREATED",
            "amount": {"currency_code": "EUR", "value": self.captured_value},
        }
        return {
            "id": PAYPAL_ORDER,
            "status": "COMPLETED",
            "purchase_units": [
                {"custom_id": self.payment_id, "payments": {kind: [item]}}
            ],
        }


@pytest.fixture
def paypal(monkeypatch: pytest.MonkeyPatch) -> FakePaypal:
    fake = FakePaypal()
    monkeypatch.setattr(paypal_module, "transport", httpx.MockTransport(fake.handler))
    monkeypatch.setattr(paypal_module, "_token_cache", {})
    monkeypatch.setattr(settings, "PAYPAL_CLIENT_ID", "client")
    monkeypatch.setattr(settings, "PAYPAL_CLIENT_SECRET", "secret")
    monkeypatch.setattr(settings, "PAYPAL_WEBHOOK_ID", "WH-1")
    monkeypatch.setattr(settings, "PAYPAL_CURRENCY", "EUR")
    monkeypatch.setattr(settings, "PAYPAL_INTENT", "CAPTURE")
    monkeypatch.setattr(
        payment_handlers, "confirm_order_stock", AsyncMock(return_value=0)
    )
    monkeypatch.setattr(payment_handlers, "issue_invoice_for_order", AsyncMock())
    return fake


async def _seed(
    session: AsyncSession, fake: FakePaypal, *, intent: str = "CAPTURE"
) -> SimpleNamespace:
    buyer = User(
        email=f"buyer+{uuid.uuid4().hex[:8]}@test.local",
        is_active=True,
        hashed_password="x",
    )
    admin = User(
        email=f"admin+{uuid.uuid4().hex[:8]}@test.local",
        is_active=True,
        is_superuser=True,
        hashed_password="x",
    )
    statuses = {name: OrderStatus(name=name) for name in ("AwaitingPayment", "Paid")}
    pending = PaymentStatus(name="Pending")
    session.add_all([buyer, admin, pending, *statuses.values()])
    await session.flush()
    order = Order(
        user_id=buyer.id,
        order_status_id=statuses["AwaitingPayment"].id,
        order_number=f"CMD-{uuid.uuid4().hex[:6]}",
        currency="XPF",
        subtotal_amount=Decimal("50000"),
        total_amount=Decimal("50000"),
    )
    session.add(order)
    await session.flush()
    payment = Payment(
        order_id=order.id,
        user_id=buyer.id,
        amount=Decimal("50000"),
        currency="XPF",
        provider_code="paypal",
        provider_reference=PAYPAL_ORDER,
        provider_data={
            "paypal_order_id": PAYPAL_ORDER,
            "intent": intent,
            "charged_amount_minor": 41900,
            "charged_currency": "EUR",
        },
        payment_status_id=pending.id,
    )
    session.add(payment)
    await session.flush()
    fake.payment_id = str(payment.id)
    seed = SimpleNamespace(
        buyer=cast(User, SimpleNamespace(id=buyer.id)),
        admin=cast(User, SimpleNamespace(id=admin.id)),
        order_id=order.id,
        payment_id=payment.id,
    )
    await session.commit()
    return seed


def _webhook(
    event_type: str, *, event_id: str, custom_id: str, value: str = "419.00"
) -> Request:
    body = json.dumps(
        {
            "id": event_id,
            "event_type": event_type,
            "resource": {
                "id": CAPTURE_ID,
                "status": "COMPLETED",
                "custom_id": custom_id,
                "amount": {"currency_code": "EUR", "value": value},
            },
        }
    ).encode()
    headers = {
        "paypal-auth-algo": "SHA256withRSA",
        "paypal-cert-url": "https://api.paypal.com/cert",
        "paypal-transmission-id": event_id,
        "paypal-transmission-sig": "sig",
        "paypal-transmission-time": "2026-09-30T10:00:00Z",
        "content-type": "application/json",
    }

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": body, "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/payments/webhooks/paypal",
        "query_string": b"",
        "headers": [(k.encode(), v.encode()) for k, v in headers.items()],
    }
    return Request(scope, receive)


async def _post_webhook(session: AsyncSession, request: Request) -> str:
    response = await process_provider_webhook(
        provider_code="paypal", session=cast(Any, session), request=request
    )
    assert response.status_code == 200
    return str(json.loads(bytes(response.body))["result"])


async def _payment(session: AsyncSession, payment_id: uuid.UUID) -> SimpleNamespace:
    session.expire_all()
    payment = await session.get(Payment, payment_id)
    assert payment is not None
    status = await session.get(PaymentStatus, payment.payment_status_id)
    return SimpleNamespace(
        status=status.name if status else None,
        data=dict(payment.provider_data or {}),
    )


async def _events(session: AsyncSession, event_type: str) -> list[dict[str, Any]]:
    rows = (
        await session.exec(
            select(OutboxEvent).where(col(OutboxEvent.type) == event_type)
        )
    ).all()
    return [dict(row.payload) for row in rows]


def test_an_xpf_amount_is_charged_in_euros_at_the_fixed_parity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "PAYPAL_CURRENCY", "EUR")
    assert charge_amount(1000, "XPF") == (Decimal("8.38"), "EUR")
    assert charge_amount(50000, "XPF") == (Decimal("419.00"), "EUR")
    assert charge_amount(1999, "EUR") == (Decimal("19.99"), "EUR")


@pytest.mark.asyncio
async def test_initiation_returns_the_approval_link(paypal: FakePaypal) -> None:
    payment_id = str(uuid.uuid4())
    result = await PaypalProvider().initiate_payment(
        InitiationRequest(
            amount=50000,
            currency="XPF",
            order_id=payment_id,
            customer_email="a@b.c",
            customer_reference="x",
            return_url="https://shop.test/paiement/retour",
        )
    )
    assert result.redirect_url and "checkoutnow" in result.redirect_url
    assert result.provider_reference == PAYPAL_ORDER
    assert result.raw_response == {
        "paypal_order_id": PAYPAL_ORDER,
        "intent": "CAPTURE",
        "charged_amount_minor": 41900,
        "charged_currency": "EUR",
    }
    _, _, body = paypal.calls[0]
    assert body is not None
    unit = body["purchase_units"][0]
    assert unit["amount"] == {"currency_code": "EUR", "value": "419.00"}
    assert unit["custom_id"] == payment_id
    context = body["payment_source"]["paypal"]["experience_context"]
    assert context["return_url"] == (
        f"https://shop.test/paiement/retour?payment={payment_id}&provider=paypal"
    )
    assert context["cancel_url"].endswith("&cancelled=1")


@pytest.mark.asyncio
async def test_confirm_captures_then_the_webhook_is_a_duplicate(
    db_session: AsyncSession, paypal: FakePaypal
) -> None:
    seed = await _seed(db_session, paypal)

    response = await confirm_my_payment(
        payment_id=seed.payment_id,
        session=cast(Any, db_session),
        current_user=cast(Any, seed.buyer),
    )
    assert response.status_name == "Completed"
    assert response.is_terminal is True
    payment = await _payment(db_session, seed.payment_id)
    assert payment.data["capture_id"] == CAPTURE_ID
    captured = await _events(db_session, "payment.captured")
    assert len(captured) == 1

    # The order follows through the usual handler.
    await payment_handlers.on_payment_captured(db_session, captured[0])
    order = await db_session.get(Order, seed.order_id)
    assert order is not None
    status = await db_session.get(OrderStatus, order.order_status_id)
    assert status is not None and status.name == "Paid"

    # Confirming again does not call PayPal again.
    calls = len(paypal.calls)
    again = await confirm_my_payment(
        payment_id=seed.payment_id,
        session=cast(Any, db_session),
        current_user=cast(Any, seed.buyer),
    )
    assert again.status_name == "Completed"
    assert len(paypal.calls) == calls

    # PayPal's notification of the same capture changes nothing.
    request = _webhook(
        "PAYMENT.CAPTURE.COMPLETED", event_id="WH-A", custom_id=str(seed.payment_id)
    )
    assert await _post_webhook(db_session, request) == "duplicate"
    # Delivered twice: recognised by its event id.
    request = _webhook(
        "PAYMENT.CAPTURE.COMPLETED", event_id="WH-A", custom_id=str(seed.payment_id)
    )
    assert await _post_webhook(db_session, request) == "duplicate"
    assert len(await _events(db_session, "payment.captured")) == 1
    recorded = (await db_session.exec(select(PaymentWebhookEvent))).all()
    assert [(e.event_id, e.outcome) for e in recorded] == [("WH-A", "duplicate")]


@pytest.mark.asyncio
async def test_confirm_is_reserved_to_the_customer(
    db_session: AsyncSession, paypal: FakePaypal
) -> None:
    seed = await _seed(db_session, paypal)
    with pytest.raises(AppError) as exc:
        await confirm_my_payment(
            payment_id=seed.payment_id,
            session=cast(Any, db_session),
            current_user=cast(Any, SimpleNamespace(id=uuid.uuid4())),
        )
    # Someone else's payment reads like an unknown one.
    assert exc.value.status_code == 404
    assert paypal.calls == []


@pytest.mark.asyncio
async def test_a_declined_instrument_fails_the_payment(
    db_session: AsyncSession, paypal: FakePaypal
) -> None:
    seed = await _seed(db_session, paypal)
    paypal.capture_issue = "INSTRUMENT_DECLINED"
    response = await confirm_my_payment(
        payment_id=seed.payment_id,
        session=cast(Any, db_session),
        current_user=cast(Any, seed.buyer),
    )
    assert response.status_name == "Failed"
    assert len(await _events(db_session, "payment.rejected")) == 1


@pytest.mark.asyncio
async def test_the_webhook_alone_completes_the_payment(
    db_session: AsyncSession, paypal: FakePaypal
) -> None:
    """The customer closed the tab after paying: PayPal's notification is
    enough."""
    seed = await _seed(db_session, paypal)
    request = _webhook(
        "PAYMENT.CAPTURE.COMPLETED", event_id="WH-B", custom_id=str(seed.payment_id)
    )
    assert await _post_webhook(db_session, request) == "applied"
    payment = await _payment(db_session, seed.payment_id)
    assert payment.status == "Completed"
    assert payment.data["capture_id"] == CAPTURE_ID

    # A contradicting notification afterwards is logged, never applied.
    request = _webhook(
        "PAYMENT.CAPTURE.DENIED", event_id="WH-C", custom_id=str(seed.payment_id)
    )
    assert await _post_webhook(db_session, request) == "conflict"
    assert (await _payment(db_session, seed.payment_id)).status == "Completed"
    assert await _events(db_session, "payment.rejected") == []


@pytest.mark.asyncio
async def test_a_wrong_amount_leaves_the_payment_for_review(
    db_session: AsyncSession, paypal: FakePaypal
) -> None:
    seed = await _seed(db_session, paypal)
    request = _webhook(
        "PAYMENT.CAPTURE.COMPLETED",
        event_id="WH-D",
        custom_id=str(seed.payment_id),
        value="1.00",
    )
    assert await _post_webhook(db_session, request) == "amount_mismatch"
    payment = await _payment(db_session, seed.payment_id)
    assert payment.status == "Pending"
    assert payment.data["amount_mismatch"]["received_minor"] == 100
    assert await _events(db_session, "payment.captured") == []


@pytest.mark.asyncio
async def test_an_unverified_notification_is_refused(
    db_session: AsyncSession, paypal: FakePaypal
) -> None:
    seed = await _seed(db_session, paypal)
    paypal.signature_ok = False
    request = _webhook(
        "PAYMENT.CAPTURE.COMPLETED", event_id="WH-E", custom_id=str(seed.payment_id)
    )
    with pytest.raises(AppError) as exc:
        await _post_webhook(db_session, request)
    assert exc.value.status_code == 400
    assert (await _payment(db_session, seed.payment_id)).status == "Pending"


@pytest.mark.asyncio
@pytest.mark.usefixtures("paypal")
async def test_a_notification_for_an_unknown_payment_is_acknowledged(
    db_session: AsyncSession,
) -> None:
    request = _webhook(
        "PAYMENT.CAPTURE.COMPLETED", event_id="WH-F", custom_id=str(uuid.uuid4())
    )
    assert await _post_webhook(db_session, request) == "unknown_payment"


@pytest.mark.asyncio
async def test_authorize_then_capture_then_refund_in_euros(
    db_session: AsyncSession, paypal: FakePaypal
) -> None:
    seed = await _seed(db_session, paypal, intent="AUTHORIZE")
    response = await confirm_my_payment(
        payment_id=seed.payment_id,
        session=cast(Any, db_session),
        current_user=cast(Any, seed.buyer),
    )
    assert response.status_name == "Authorized"
    assert (await _payment(db_session, seed.payment_id)).data[
        "authorization_id"
    ] == AUTHORIZATION_ID

    db_session.add(PaymentStatus(name="Completed"))
    await db_session.commit()
    payment = await db_session.get(Payment, seed.payment_id)
    assert payment is not None
    await capture_payment(db_session, payment=payment, admin=seed.admin)
    after = await _payment(db_session, seed.payment_id)
    assert after.status == "Completed"
    assert after.data["capture_id"] == CAPTURE_ID
    assert _last_path(paypal) == (
        f"/v2/payments/authorizations/{AUTHORIZATION_ID}/capture"
    )

    db_session.add_all(
        [PaymentStatus(name="Refunded"), PaymentStatus(name="PartiallyRefunded")]
    )
    await db_session.commit()
    payment = await db_session.get(Payment, seed.payment_id)
    assert payment is not None
    outcome = await refund_payment(
        db_session, payment=payment, admin=seed.admin, amount=Decimal("10000")
    )
    assert outcome.message == "Remboursement PayPal effectué."
    method, path, body = paypal.calls[-1]
    assert (method, path) == ("POST", f"/v2/payments/captures/{CAPTURE_ID}/refund")
    assert body is not None
    assert body["amount"] == {"currency_code": "EUR", "value": "83.80"}


def _last_path(fake: FakePaypal) -> str:
    return fake.calls[-1][1]
