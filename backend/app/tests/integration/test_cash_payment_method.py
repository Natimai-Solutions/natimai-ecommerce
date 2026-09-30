"""Cash at the office (R3-P1) and deposits for every method (R3-P3).

Real database: the manual « Espèces » method, the shop's own instructions
replacing the default text, the order e-mail repeating them, and a method the
shop excluded from deposits.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.errors import AppError
from app.features.notification.email_renderer import render_email
from app.features.payment.models.payment_method import PaymentMethod
from app.features.payment.models.payment_status import PaymentStatus
from app.features.payment.providers import ManualCashProvider, get_provider
from app.features.payment.services.payment_initiation import (
    initiate_payment_for_method,
)
from app.features.system.models.system_setting import SystemSetting
from app.features.user.models.user import User


async def _customer(session: AsyncSession) -> Any:
    user = User(
        email=f"client+{uuid.uuid4().hex[:8]}@test.local",
        full_name="Moana Client",
        is_active=True,
        hashed_password="x",
    )
    session.add(user)
    await session.flush()
    # A snapshot: every commit of the test expires the ORM instance.
    snapshot = SimpleNamespace(
        id=user.id, email=user.email, full_name=user.full_name, price_group_id=None
    )
    await session.commit()
    return snapshot


async def _method(
    session: AsyncSession, provider_code: str, *, deposit_allowed: bool = True
) -> uuid.UUID:
    method = PaymentMethod(
        name=provider_code,
        provider_code=provider_code,
        requires_admin_validation=True,
        deposit_allowed=deposit_allowed,
    )
    session.add(method)
    await session.flush()
    method_id = method.id
    await session.commit()
    return method_id


def test_cash_is_a_registered_manual_provider() -> None:
    provider = get_provider("manual_cash")
    assert isinstance(provider, ManualCashProvider)
    assert "espèces" in provider.instructions.lower()


@pytest.mark.asyncio
async def test_cash_payment_waits_for_the_office_with_default_instructions(
    db_session: AsyncSession,
) -> None:
    user = await _customer(db_session)
    method_id = await _method(db_session, "manual_cash")

    result = await initiate_payment_for_method(
        db_session,
        payment_method_id=method_id,
        amount=Decimal("12000"),
        currency="XPF",
        order_id=None,
        return_url=None,
        metadata=None,
        current_user=user,
    )
    status_id = result.payment.payment_status_id
    await db_session.commit()

    assert result.provider_code == "manual_cash"
    assert result.instructions == ManualCashProvider.instructions
    status = await db_session.get(PaymentStatus, status_id)
    assert status is not None and status.name == "AwaitingValidation"


@pytest.mark.asyncio
async def test_shop_instructions_replace_the_default_text(
    db_session: AsyncSession,
) -> None:
    user = await _customer(db_session)
    method_id = await _method(db_session, "manual_cash")
    office = (
        "Bureau Natimai, rue des Remparts, Papeete — du lundi au vendredi, 8 h - 16 h"
    )
    db_session.add(SystemSetting(key="payment_instructions_manual_cash", value=office))
    # An empty setting keeps the provider's text.
    db_session.add(SystemSetting(key="payment_instructions_manual_check", value="  "))
    await db_session.commit()

    cash = await initiate_payment_for_method(
        db_session,
        payment_method_id=method_id,
        amount=Decimal("12000"),
        currency="XPF",
        order_id=None,
        return_url=None,
        metadata=None,
        current_user=user,
    )
    assert cash.instructions == office

    check_id = await _method(db_session, "manual_check")
    check = await initiate_payment_for_method(
        db_session,
        payment_method_id=check_id,
        amount=Decimal("12000"),
        currency="XPF",
        order_id=None,
        return_url=None,
        metadata=None,
        current_user=user,
    )
    assert check.instructions is not None and "chèque" in check.instructions


@pytest.mark.asyncio
async def test_a_method_excluded_from_deposits_cannot_pay_one(
    db_session: AsyncSession,
) -> None:
    user = await _customer(db_session)
    check_id = await _method(db_session, "manual_check", deposit_allowed=False)

    with pytest.raises(AppError) as refused:
        await initiate_payment_for_method(
            db_session,
            payment_method_id=check_id,
            amount=Decimal("3000"),
            currency="XPF",
            order_id=None,
            return_url=None,
            metadata=None,
            current_user=user,
            kind="deposit",
        )
    assert refused.value.code == "payment.method.deposit_not_allowed"

    # The same method still settles a balance or a full payment.
    for kind in ("balance", "full"):
        result = await initiate_payment_for_method(
            db_session,
            payment_method_id=check_id,
            amount=Decimal("3000"),
            currency="XPF",
            order_id=None,
            return_url=None,
            metadata=None,
            current_user=user,
            kind=kind,
        )
        assert result.payment.kind == kind


@pytest.mark.parametrize("fmt", ["text", "html"])
def test_order_email_repeats_how_to_pay(fmt: str) -> None:
    email = render_email(
        "order_created",
        full_name="Moana",
        order_id=str(uuid.uuid4()),
        order_ref="CMD-2026-00042",
        total_amount="50000",
        amount_due_now="15000",
        currency="XPF",
        item_count=2,
        tracking_url="",
        payment_instructions="Bureau <Natimai>\nPapeete",
        shop_name="Natimai",
    )
    body = email.text if fmt == "text" else email.html
    assert "Pour régler votre commande" in body
    assert "15000 XPF maintenant" in body
    if fmt == "html":
        # Admin-entered text is escaped in the HTML part.
        assert "Bureau &lt;Natimai&gt;" in body
    else:
        assert "Bureau <Natimai>\nPapeete" in body


def test_order_email_without_instructions_is_unchanged() -> None:
    email = render_email(
        "order_created",
        full_name="Moana",
        order_id=str(uuid.uuid4()),
        order_ref="CMD-2026-00042",
        total_amount="50000",
        amount_due_now="50000",
        currency="XPF",
        item_count=2,
        tracking_url="",
        payment_instructions="",
        shop_name="Natimai",
    )
    assert "Pour régler" not in email.text
