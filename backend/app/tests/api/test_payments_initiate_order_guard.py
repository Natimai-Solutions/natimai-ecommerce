"""Server-side revalidation of ``POST /payments/initiate`` (S1 audit fix).

The client-supplied amount, currency and order_id must never be trusted: the
order has to exist, belong to the caller, still be payable, and the amount must
equal the order total snapshotted at checkout.
"""

from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api.routes.payments import PaymentsInitiateRequest, initiate_payment
from app.core.errors import AppError
from app.features.order.models.order import Order
from app.features.order.models.order_status import OrderStatus
from app.features.payment.crud.payment import crud_payment


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _make_session(order: Any, order_status: Any = None) -> Any:
    session = AsyncMock()
    session.add = Mock()

    async def _get(model: Any, _key: Any) -> Any:
        if model is Order:
            return order
        if model is OrderStatus:
            return order_status
        raise AssertionError(f"unexpected session.get({model!r})")

    session.get = _get
    return session


def _make_user() -> Any:
    return SimpleNamespace(
        id=uuid4(),
        email="client@example.com",
        full_name="Jane Doe",
        price_group_id=None,
    )


def _make_request(
    *,
    order_id: Any,
    amount: Decimal = Decimal("25000"),
    currency: str = "XPF",
) -> PaymentsInitiateRequest:
    return PaymentsInitiateRequest(
        payment_method_id=uuid4(),
        amount=amount,
        currency=currency,
        order_id=order_id,
    )


def _patch_initiation_service(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    service_mock = AsyncMock()
    monkeypatch.setattr(
        "app.api.routes.payments.initiate_payment_for_method",
        service_mock,
    )
    return service_mock


@pytest.mark.anyio
async def test_initiate_rejects_unknown_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _make_session(order=None)
    service_mock = _patch_initiation_service(monkeypatch)

    with pytest.raises(AppError) as exc_info:
        await initiate_payment(
            session=session,
            request=_make_request(order_id=uuid4()),
            current_user=cast(Any, _make_user()),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "payment.order.not_found"
    service_mock.assert_not_awaited()


@pytest.mark.anyio
async def test_initiate_rejects_foreign_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An order belonging to another user is reported exactly like a missing
    one, so order ids cannot be probed."""
    order = SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),  # not the caller
        order_status_id=uuid4(),
        total_amount=Decimal("25000.00"),
    )
    session = _make_session(order=order)
    service_mock = _patch_initiation_service(monkeypatch)

    with pytest.raises(AppError) as exc_info:
        await initiate_payment(
            session=session,
            request=_make_request(order_id=order.id),
            current_user=cast(Any, _make_user()),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "payment.order.not_found"
    service_mock.assert_not_awaited()


@pytest.mark.anyio
async def test_initiate_rejects_already_paid_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _make_user()
    order = SimpleNamespace(
        id=uuid4(),
        user_id=user.id,
        order_status_id=uuid4(),
        total_amount=Decimal("25000.00"),
    )
    session = _make_session(order=order, order_status=SimpleNamespace(name="Paid"))
    service_mock = _patch_initiation_service(monkeypatch)

    with pytest.raises(AppError) as exc_info:
        await initiate_payment(
            session=session,
            request=_make_request(order_id=order.id),
            current_user=cast(Any, user),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "payment.order.not_payable"
    service_mock.assert_not_awaited()


@pytest.mark.anyio
async def test_initiate_rejects_amount_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The 1-XPF-payment attack: the client amount must equal the order total."""
    user = _make_user()
    order = SimpleNamespace(
        id=uuid4(),
        user_id=user.id,
        order_status_id=uuid4(),
        total_amount=Decimal("25000.00"),
    )
    session = _make_session(
        order=order, order_status=SimpleNamespace(name="AwaitingPayment")
    )
    monkeypatch.setattr(crud_payment, "get_by_order_id", AsyncMock(return_value=None))
    service_mock = _patch_initiation_service(monkeypatch)

    with pytest.raises(AppError) as exc_info:
        await initiate_payment(
            session=session,
            request=_make_request(order_id=order.id, amount=Decimal("1")),
            current_user=cast(Any, user),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "payment.amount.mismatch"
    assert exc_info.value.details["expected_amount"] == "25000"
    service_mock.assert_not_awaited()


@pytest.mark.anyio
async def test_initiate_rejects_currency_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _make_user()
    order = SimpleNamespace(
        id=uuid4(),
        user_id=user.id,
        order_status_id=uuid4(),
        total_amount=Decimal("25000.00"),
    )
    session = _make_session(
        order=order, order_status=SimpleNamespace(name="AwaitingPayment")
    )
    monkeypatch.setattr(
        crud_payment,
        "get_by_order_id",
        AsyncMock(return_value=SimpleNamespace(currency="XPF")),
    )
    service_mock = _patch_initiation_service(monkeypatch)

    with pytest.raises(AppError) as exc_info:
        await initiate_payment(
            session=session,
            request=_make_request(
                order_id=order.id, amount=Decimal("209.00"), currency="EUR"
            ),
            current_user=cast(Any, user),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "payment.currency.mismatch"
    assert exc_info.value.details["expected_currency"] == "XPF"
    service_mock.assert_not_awaited()


@pytest.mark.anyio
async def test_initiate_accepts_matching_order_payment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _make_user()
    order = SimpleNamespace(
        id=uuid4(),
        user_id=user.id,
        order_status_id=uuid4(),
        total_amount=Decimal("25000.00"),
    )
    session = _make_session(
        order=order, order_status=SimpleNamespace(name="AwaitingPayment")
    )
    monkeypatch.setattr(
        crud_payment,
        "get_by_order_id",
        AsyncMock(return_value=SimpleNamespace(currency="XPF")),
    )

    payment = SimpleNamespace(id=uuid4())
    service_mock = AsyncMock(
        return_value=SimpleNamespace(
            payment=payment,
            provider_code="payzen",
            provider_reference="tx-1",
            form_token="tok",
            server_url="https://static.osb.pf",
            public_key="pk",
            redirect_url=None,
            instructions=None,
        )
    )
    monkeypatch.setattr(
        "app.api.routes.payments.initiate_payment_for_method",
        service_mock,
    )

    response = await initiate_payment(
        session=session,
        request=_make_request(order_id=order.id),
        current_user=cast(Any, user),
    )

    assert response.payment_id == payment.id
    assert response.provider_code == "payzen"
    service_mock.assert_awaited_once()
    assert service_mock.await_args is not None
    assert service_mock.await_args.kwargs["amount"] == Decimal("25000")
    assert service_mock.await_args.kwargs["order_id"] == order.id
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()
