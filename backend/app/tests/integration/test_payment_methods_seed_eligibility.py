"""Integration tests: payment method seeding + global availability (item 6).

- The seed creates a card (PayZen/CB) method so it appears at checkout.
- ``get_eligible_payment_methods`` excludes methods disabled globally by an admin
  (``is_admin_active=False``).
"""

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.initial_data import _seed_manual_payment_methods
from app.features.payment.models.payment_method import PaymentMethod
from app.features.payment.services.eligibility import get_eligible_payment_methods


@pytest.mark.asyncio
async def test_seed_creates_card_payment_method(db_session: AsyncSession) -> None:
    await _seed_manual_payment_methods(db_session)

    result = await db_session.exec(
        select(PaymentMethod).where(PaymentMethod.provider_code == "payzen")
    )
    card = result.first()
    assert card is not None
    assert card.name == "Carte bancaire"


@pytest.mark.asyncio
async def test_eligibility_excludes_globally_disabled(
    db_session: AsyncSession,
) -> None:
    enabled = PaymentMethod(
        name="Chèque",
        provider_code="manual_check",
        is_admin_active=True,
    )
    disabled = PaymentMethod(
        name="Virement (désactivé)",
        provider_code="manual_transfer",
        is_admin_active=False,
    )
    db_session.add_all([enabled, disabled])
    await db_session.flush()
    enabled_id, disabled_id = enabled.id, disabled.id

    # No price group / no eligibility rows → every globally-active method is open.
    eligible = await get_eligible_payment_methods(db_session, price_group_id=None)

    eligible_ids = {method.id for method in eligible}
    assert enabled_id in eligible_ids
    assert disabled_id not in eligible_ids
