from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import Request

from app.api.routes.payments import (
    _sync_checkout_entities_for_payzen_status,
    payzen_ipn,
)
from app.features.order.crud.order_crud import crud_order
from app.features.order.crud.order_status_crud import crud_order_status
from app.features.payment.crud.payment import crud_payment
from app.features.payment.crud.payment_status import crud_payment_status
from app.features.payment.models.payment import Payment


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_sync_checkout_entities_sets_paid_statuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.add = Mock()

    order_id = uuid4()
    payment = cast(
        Payment,
        SimpleNamespace(id=uuid4(), order_id=order_id, payment_status_id=None),
    )
    order = SimpleNamespace(id=order_id, order_status_id=None)

    completed_payment_status = SimpleNamespace(id=uuid4())
    paid_order_status = SimpleNamespace(id=uuid4())

    monkeypatch.setattr(
        crud_payment_status,
        "get_by_name",
        AsyncMock(return_value=completed_payment_status),
    )
    monkeypatch.setattr(
        crud_order,
        "read",
        AsyncMock(return_value=order),
    )
    monkeypatch.setattr(
        crud_order_status,
        "get_by_name",
        AsyncMock(return_value=paid_order_status),
    )

    await _sync_checkout_entities_for_payzen_status(
        session=session,
        payment=payment,
        trans_status="PAID",
    )

    assert payment.payment_status_id == completed_payment_status.id
    assert order.order_status_id == paid_order_status.id


@pytest.mark.anyio
async def test_sync_checkout_entities_sets_failed_statuses_and_creates_if_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.add = Mock()

    order_id = uuid4()
    payment = cast(
        Payment,
        SimpleNamespace(id=uuid4(), order_id=order_id, payment_status_id=None),
    )
    order = SimpleNamespace(id=order_id, order_status_id=None)

    created_payment_status = SimpleNamespace(id=uuid4())
    created_order_status = SimpleNamespace(id=uuid4())

    monkeypatch.setattr(
        crud_payment_status,
        "get_by_name",
        AsyncMock(return_value=None),
    )
    create_payment_status_mock = AsyncMock(return_value=created_payment_status)
    monkeypatch.setattr(
        crud_payment_status,
        "create_draft",
        create_payment_status_mock,
    )

    monkeypatch.setattr(
        crud_order,
        "read",
        AsyncMock(return_value=order),
    )
    monkeypatch.setattr(
        crud_order_status,
        "get_by_name",
        AsyncMock(return_value=None),
    )
    create_order_status_mock = AsyncMock(return_value=created_order_status)
    monkeypatch.setattr(
        crud_order_status,
        "create_draft",
        create_order_status_mock,
    )

    await _sync_checkout_entities_for_payzen_status(
        session=session,
        payment=payment,
        trans_status="REFUSED",
    )

    assert payment.payment_status_id == created_payment_status.id
    assert order.order_status_id == created_order_status.id
    create_payment_status_mock.assert_awaited_once()
    create_order_status_mock.assert_awaited_once()


@pytest.mark.anyio
async def test_sync_checkout_entities_ignores_unknown_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.add = Mock()

    payment = cast(
        Payment,
        SimpleNamespace(
            id=uuid4(),
            order_id=uuid4(),
            payment_status_id=None,
            payzen_status=None,
            payzen_trans_id=None,
        ),
    )

    get_order_mock = AsyncMock(
        return_value=SimpleNamespace(id=uuid4(), order_status_id=None)
    )
    monkeypatch.setattr(crud_order, "read", get_order_mock)

    await _sync_checkout_entities_for_payzen_status(
        session=session,
        payment=payment,
        trans_status="UNDER_REVIEW",
    )

    assert payment.payment_status_id is None
    get_order_mock.assert_not_awaited()


@pytest.mark.anyio
async def test_payzen_ipn_applies_c5_sync_in_single_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.add = Mock()

    payment = cast(
        Payment,
        SimpleNamespace(
            id=uuid4(),
            order_id=uuid4(),
            payment_status_id=None,
            payzen_status=None,
            payzen_trans_id=None,
        ),
    )

    monkeypatch.setattr(
        "app.api.routes.payments.validate_ipn_signature",
        Mock(
            return_value={
                "order_id": str(payment.id),
                "trans_status": "PAID",
                "amount": "1500",
                "payment_cards": "VISA",
                "_raw_answer": {},
            }
        ),
    )
    monkeypatch.setattr(
        crud_payment,
        "get_by_payzen_order_id",
        AsyncMock(return_value=payment),
    )

    update_payment_mock = AsyncMock(return_value=payment)
    monkeypatch.setattr(
        crud_payment,
        "update_payment_from_payzen",
        update_payment_mock,
    )

    sync_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "app.api.routes.payments._sync_checkout_entities_for_payzen_status",
        sync_mock,
    )

    request = cast(
        Request,
        SimpleNamespace(form=AsyncMock(return_value={"kr-answer": "ignored"})),
    )
    response = await payzen_ipn(session=session, request=request)

    assert response.status_code == 200

    assert update_payment_mock.await_args is not None
    update_kwargs = update_payment_mock.await_args.kwargs
    assert update_kwargs["commit"] is False

    sync_mock.assert_awaited_once()
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()
