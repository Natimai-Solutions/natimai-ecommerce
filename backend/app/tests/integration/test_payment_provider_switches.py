"""Payment service providers switched on and off in base (R3-P5)."""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.admin_payment_providers import (
    PaymentProviderUpdate,
    list_payment_providers,
    update_payment_provider,
)
from app.core.config import settings
from app.core.errors import AppError
from app.features.payment.models.payment_method import PaymentMethod
from app.features.payment.services.eligibility import get_eligible_payment_methods
from app.features.payment.services.payment_initiation import (
    initiate_payment_for_method,
)
from app.features.payment.services.provider_settings import (
    provider_available,
    set_provider_enabled,
)
from app.features.user.models.user import User

ADMIN = cast(User, SimpleNamespace(id=uuid.uuid4(), is_superuser=True))


@pytest.fixture
def payzen_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "PAYZEN_SITE_ID", "12345678")
    monkeypatch.setattr(settings, "PAYZEN_API_PASSWORD_TEST", "testpassword_x")
    monkeypatch.setattr(settings, "PAYZEN_MODE", "TEST")


async def _methods(session: AsyncSession) -> None:
    session.add_all(
        [
            PaymentMethod(name="Carte", provider_code="payzen", sort_order=1),
            PaymentMethod(name="PayPal", provider_code="paypal", sort_order=2),
            PaymentMethod(
                name="Espèces",
                provider_code="manual_cash",
                sort_order=3,
                requires_admin_validation=True,
            ),
        ]
    )
    await session.commit()


async def _names(session: AsyncSession) -> list[str]:
    methods = await get_eligible_payment_methods(session, price_group_id=None)
    return [m.name for m in methods]


@pytest.mark.asyncio
async def test_a_provider_without_credentials_is_hidden(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "PAYZEN_SITE_ID", None)
    await _methods(db_session)
    # PayZen is on by default but has no credentials; PayPal is off by default.
    assert await _names(db_session) == ["Espèces"]
    assert await provider_available(db_session, "payzen") is False


@pytest.mark.asyncio
@pytest.mark.usefixtures("payzen_credentials")
async def test_switching_payzen_off_hides_and_refuses_the_card(
    db_session: AsyncSession,
) -> None:
    await _methods(db_session)
    assert await _names(db_session) == ["Carte", "Espèces"]

    await set_provider_enabled(db_session, "payzen", False)
    await db_session.commit()
    assert await _names(db_session) == ["Espèces"]

    card = next(
        m.id for m in await _all_methods(db_session) if m.provider_code == "payzen"
    )
    user = await _customer(db_session)
    with pytest.raises(AppError) as refused:
        await initiate_payment_for_method(
            db_session,
            payment_method_id=card,
            amount=Decimal("1000"),
            currency="XPF",
            order_id=None,
            return_url=None,
            metadata=None,
            current_user=user,
        )
    assert refused.value.code == "payment.provider.disabled"

    # Back on: the card is offered again, no restart needed.
    await set_provider_enabled(db_session, "payzen", True)
    await db_session.commit()
    assert await _names(db_session) == ["Carte", "Espèces"]


@pytest.mark.asyncio
@pytest.mark.usefixtures("payzen_credentials")
async def test_paypal_needs_its_switch_and_its_credentials(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _methods(db_session)
    await set_provider_enabled(db_session, "paypal", True)
    await db_session.commit()
    monkeypatch.setattr(settings, "PAYPAL_CLIENT_ID", None)
    assert "PayPal" not in await _names(db_session)

    monkeypatch.setattr(settings, "PAYPAL_CLIENT_ID", "client")
    monkeypatch.setattr(settings, "PAYPAL_CLIENT_SECRET", "secret")
    assert await _names(db_session) == ["Carte", "PayPal", "Espèces"]


@pytest.mark.asyncio
@pytest.mark.usefixtures("payzen_credentials")
async def test_admin_lists_and_switches_providers(db_session: AsyncSession) -> None:
    providers = {p.code: p for p in await list_payment_providers(db_session, ADMIN)}
    assert set(providers) == {"payzen", "paypal", "stripe"}
    assert providers["payzen"].available is True
    assert providers["stripe"].implemented is False

    updated = await update_payment_provider(
        "PayZen", PaymentProviderUpdate(enabled=False), db_session, ADMIN
    )
    assert {p.code: p.enabled for p in updated}["payzen"] is False

    with pytest.raises(AppError) as unknown:
        await update_payment_provider(
            "cash", PaymentProviderUpdate(enabled=False), db_session, ADMIN
        )
    assert unknown.value.status_code == 404


async def _all_methods(session: AsyncSession) -> list[Any]:
    from sqlmodel import select

    rows = await session.exec(select(PaymentMethod.id, PaymentMethod.provider_code))
    return [SimpleNamespace(id=i, provider_code=c) for i, c in rows.all()]


async def _customer(session: AsyncSession) -> Any:
    user = User(email=f"c+{uuid.uuid4().hex[:6]}@t.local", hashed_password="x")
    session.add(user)
    await session.flush()
    snapshot = SimpleNamespace(
        id=user.id, email=user.email, full_name=None, price_group_id=None
    )
    await session.commit()
    return snapshot
