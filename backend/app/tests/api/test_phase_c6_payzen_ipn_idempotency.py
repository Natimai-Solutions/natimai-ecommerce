import json
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import Request

from app.api.routes.payzen import payzen_ipn
from app.features.payment.crud.payment import crud_payment
from app.features.payment.models.payment import Payment


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_payzen_ipn_ignores_duplicate_terminal_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.add = Mock()

    payment = cast(
        Payment,
        SimpleNamespace(
            id=uuid4(),
            order_id=uuid4(),
            payzen_status="PAID",
            payzen_trans_id="tx-001",
            payment_status_id=None,
        ),
    )

    monkeypatch.setattr(
        "app.api.routes.payzen.validate_ipn_signature",
        Mock(
            return_value={
                "order_id": str(payment.id),
                "trans_status": "PAID",
                "trans_uuid": "tx-001",
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
        "app.api.routes.payzen._sync_checkout_entities_for_payzen_status",
        sync_mock,
    )

    request = cast(
        Request,
        SimpleNamespace(form=AsyncMock(return_value={"kr-answer": "ignored"})),
    )
    response = await payzen_ipn(session=session, request=request)

    assert response.status_code == 200
    payload = json.loads(bytes(response.body).decode("utf-8"))
    assert payload["status"] == "ok"
    assert payload["message"] == "IPN deja traite"

    update_payment_mock.assert_not_awaited()
    sync_mock.assert_not_awaited()
    session.commit.assert_not_awaited()
    session.rollback.assert_not_awaited()


@pytest.mark.anyio
async def test_payzen_ipn_ignores_conflicting_terminal_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.add = Mock()

    payment = cast(
        Payment,
        SimpleNamespace(
            id=uuid4(),
            order_id=uuid4(),
            payzen_status="PAID",
            payzen_trans_id="tx-paid",
            payment_status_id=None,
        ),
    )

    monkeypatch.setattr(
        "app.api.routes.payzen.validate_ipn_signature",
        Mock(
            return_value={
                "order_id": str(payment.id),
                "trans_status": "REFUSED",
                "trans_uuid": "tx-refused",
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
        "app.api.routes.payzen._sync_checkout_entities_for_payzen_status",
        sync_mock,
    )

    request = cast(
        Request,
        SimpleNamespace(form=AsyncMock(return_value={"kr-answer": "ignored"})),
    )
    response = await payzen_ipn(session=session, request=request)

    assert response.status_code == 200
    payload = json.loads(bytes(response.body).decode("utf-8"))
    assert payload["status"] == "ok"
    assert payload["message"] == "IPN terminal contradictoire ignore"

    update_payment_mock.assert_not_awaited()
    sync_mock.assert_not_awaited()
    session.commit.assert_not_awaited()
    session.rollback.assert_not_awaited()
