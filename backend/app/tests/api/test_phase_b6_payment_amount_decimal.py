"""Phase B6 — payment amount alignment on Decimal.

Verifies that the PayZen → Payment conversion preserves the Decimal
representation expected by the rest of the domain (Order, OrderLine,
Product), and that the amount is correctly translated from PayZen's
minor units regardless of the currency scale.
"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.features.payment.crud.payment import crud_payment
from app.features.payment.models.payment import PaymentBase
from app.features.payment.models.payment_log import PaymentLogBase


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_payment_base_amount_is_decimal() -> None:
    field = PaymentBase.model_fields["amount"]
    assert field.annotation is Decimal


def test_payment_log_base_amount_is_decimal() -> None:
    field = PaymentLogBase.model_fields["amount"]
    assert field.annotation is Decimal


@pytest.mark.anyio
async def test_update_payment_from_payzen_converts_eur_minor_units_to_decimal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payment = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000001",
        amount=Decimal("0.00"),
        currency="EUR",
        payzen_trans_id=None,
        payzen_order_id=None,
        payzen_status=None,
        payzen_payment_method=None,
        payzen_data=None,
        payzen_error_code=None,
        payment_status_id=None,
    )
    session = AsyncMock()

    monkeypatch.setattr(
        "app.features.payment.crud.payment_status.crud_payment_status."
        "get_by_name",
        AsyncMock(return_value=None),
    )

    payzen_fields = {
        "amount": "1250",
        "trans_uuid": "trans-uuid",
        "trans_status": "PAID",
        "order_id": "order-1",
        "payment_cards": "VISA",
        "_raw_answer": {},
    }

    updated = await crud_payment.update_payment_from_payzen(
        session=session,
        payment=payment,
        payzen_fields=payzen_fields,
        commit=False,
    )

    assert updated.amount == Decimal("12.50")
    assert isinstance(updated.amount, Decimal)


@pytest.mark.anyio
async def test_update_payment_from_payzen_preserves_xpf_zero_decimal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payment = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000002",
        amount=Decimal("0.00"),
        currency="XPF",
        payzen_trans_id=None,
        payzen_order_id=None,
        payzen_status=None,
        payzen_payment_method=None,
        payzen_data=None,
        payzen_error_code=None,
        payment_status_id=None,
    )
    session = AsyncMock()

    monkeypatch.setattr(
        "app.features.payment.crud.payment_status.crud_payment_status."
        "get_by_name",
        AsyncMock(return_value=None),
    )

    payzen_fields = {
        "amount": "1500",
        "trans_uuid": "trans-uuid",
        "trans_status": "PAID",
        "order_id": "order-2",
        "payment_cards": "VISA",
        "_raw_answer": {},
    }

    updated = await crud_payment.update_payment_from_payzen(
        session=session,
        payment=payment,
        payzen_fields=payzen_fields,
        commit=False,
    )

    assert updated.amount == Decimal("1500")
    assert isinstance(updated.amount, Decimal)
