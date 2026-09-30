"""Éligibilité des moyens de paiement (Q3) — service + route admin, vraie base.

Les règles : un moyen sans ligne d'éligibilité est ouvert à tous ; dès qu'il
en a une, il est réservé aux groupes listés ; ``max_amount`` le masque au-delà
d'un montant ; sans groupe, on retombe sur le groupe par défaut. C'est ce
filtrage groupe × montant qui décide de ce qu'un client voit au checkout — il
n'avait qu'un test (désactivation globale).
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, cast

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.admin_payment_eligibility import (
    add_eligible_group,
    list_eligible_groups,
    remove_eligible_group,
)
from app.core.config import settings
from app.core.errors import AppError
from app.features.payment.models.payment_method import PaymentMethod
from app.features.payment.models.payment_method_eligibility import (
    PaymentMethodEligibility,
)
from app.features.payment.services.eligibility import (
    check_payment_method_eligible,
    get_default_price_group_id,
    get_eligible_payment_methods,
)
from app.features.product.models.price_group import PriceGroup
from app.features.user.models.user import User


@pytest.fixture(autouse=True)
def _payzen_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """The card provider has credentials here (an unconfigured provider is
    hidden from the checkout, see provider_settings)."""
    monkeypatch.setattr(settings, "PAYZEN_SITE_ID", "12345678")
    monkeypatch.setattr(settings, "PAYZEN_API_PASSWORD_TEST", "testpassword_x")
    monkeypatch.setattr(settings, "PAYZEN_MODE", "TEST")


async def _seed(session: AsyncSession) -> dict[str, uuid.UUID]:
    """Deux groupes (défaut + pro), trois moyens : ouvert, réservé aux pros,
    plafonné."""
    default = PriceGroup(code="PART", label="Particulier", default=True)
    pro = PriceGroup(code="PRO", label="Pro")
    session.add_all([default, pro])
    await session.flush()

    open_method = PaymentMethod(
        name="Chèque", provider_code="manual_check", sort_order=3
    )
    pro_only = PaymentMethod(
        name="Bon de commande", provider_code="document", sort_order=1
    )
    capped = PaymentMethod(
        name="Carte",
        provider_code="payzen",
        sort_order=2,
        max_amount=Decimal("100000.00"),
    )
    session.add_all([open_method, pro_only, capped])
    await session.flush()
    session.add(
        PaymentMethodEligibility(payment_method_id=pro_only.id, price_group_id=pro.id)
    )
    await session.flush()
    return {
        "default": default.id,
        "pro": pro.id,
        "open": open_method.id,
        "pro_only": pro_only.id,
        "capped": capped.id,
    }


async def _names(session: AsyncSession, **kwargs: Any) -> list[str]:
    return [m.name for m in await get_eligible_payment_methods(session, **kwargs)]


@pytest.mark.asyncio
async def test_restricted_methods_are_hidden_from_other_groups(
    db_session: AsyncSession,
) -> None:
    ids = await _seed(db_session)

    # Trié par sort_order : Carte (2) avant Chèque (3).
    assert await _names(db_session, price_group_id=ids["default"]) == [
        "Carte",
        "Chèque",
    ]
    assert await _names(db_session, price_group_id=ids["pro"]) == [
        "Bon de commande",
        "Carte",
        "Chèque",
    ]


@pytest.mark.asyncio
async def test_no_group_falls_back_to_the_default_group(
    db_session: AsyncSession,
) -> None:
    ids = await _seed(db_session)
    assert await get_default_price_group_id(db_session) == ids["default"]

    # Un client sans groupe voit ce que voit le groupe par défaut.
    assert await _names(db_session, price_group_id=None) == ["Carte", "Chèque"]

    # Sans groupe par défaut du tout : seuls les moyens ouverts restent.
    default = await db_session.get(PriceGroup, ids["default"])
    assert default is not None
    default.default = False
    db_session.add(default)
    await db_session.flush()
    assert await get_default_price_group_id(db_session) is None
    assert await _names(db_session, price_group_id=None) == ["Carte", "Chèque"]
    # …et un groupe inconnu ne débloque rien de réservé.
    assert await _names(db_session, price_group_id=uuid.uuid4()) == ["Carte", "Chèque"]


@pytest.mark.asyncio
async def test_max_amount_hides_the_method_above_the_cap(
    db_session: AsyncSession,
) -> None:
    ids = await _seed(db_session)

    under = await _names(
        db_session, price_group_id=ids["pro"], cart_total=Decimal("100000.00")
    )
    over = await _names(
        db_session, price_group_id=ids["pro"], cart_total=Decimal("100000.01")
    )
    assert "Carte" in under
    assert "Carte" not in over
    assert over == ["Bon de commande", "Chèque"]

    # Même verdict à l'initiation du paiement (garde serveur, pas seulement l'affichage).
    assert (
        await check_payment_method_eligible(
            db_session,
            payment_method_id=ids["capped"],
            price_group_id=ids["pro"],
            amount=Decimal("250000.00"),
        )
        is False
    )
    assert (
        await check_payment_method_eligible(
            db_session,
            payment_method_id=ids["pro_only"],
            price_group_id=ids["default"],
            amount=Decimal("10.00"),
        )
        is False
    )
    assert (
        await check_payment_method_eligible(
            db_session,
            payment_method_id=ids["pro_only"],
            price_group_id=ids["pro"],
            amount=Decimal("10.00"),
        )
        is True
    )


@pytest.mark.asyncio
async def test_nothing_active_means_nothing_eligible(db_session: AsyncSession) -> None:
    assert await get_eligible_payment_methods(db_session, price_group_id=None) == []


async def _admin(session: AsyncSession) -> Any:
    admin = User(
        email=f"admin+{uuid.uuid4().hex[:8]}@test.local",
        is_superuser=True,
        hashed_password="x",
    )
    session.add(admin)
    await session.flush()
    return cast(Any, admin)


@pytest.mark.asyncio
async def test_admin_can_open_and_close_a_method_to_a_group(
    db_session: AsyncSession,
) -> None:
    ids = await _seed(db_session)
    admin = await _admin(db_session)

    # Le moyen ouvert n'a aucune restriction : liste vide.
    assert await list_eligible_groups(ids["open"], db_session, admin) == []

    # Réserver le chèque aux pros — idempotent.
    await add_eligible_group(ids["open"], ids["pro"], db_session, admin)
    await add_eligible_group(ids["open"], ids["pro"], db_session, admin)
    groups = await list_eligible_groups(ids["open"], db_session, admin)
    assert [g["code"] for g in groups] == ["PRO"]
    assert "Chèque" not in await _names(db_session, price_group_id=ids["default"])

    # Lever la restriction — idempotent aussi, la seconde fois ne trouve rien.
    await remove_eligible_group(ids["open"], ids["pro"], db_session, admin)
    await remove_eligible_group(ids["open"], ids["pro"], db_session, admin)
    assert await list_eligible_groups(ids["open"], db_session, admin) == []
    assert "Chèque" in await _names(db_session, price_group_id=ids["default"])


@pytest.mark.asyncio
async def test_admin_eligibility_rejects_unknown_ids(db_session: AsyncSession) -> None:
    ids = await _seed(db_session)
    admin = await _admin(db_session)

    with pytest.raises(AppError) as exc:
        await list_eligible_groups(uuid.uuid4(), db_session, admin)
    assert exc.value.code == "payment.method.not_found"

    with pytest.raises(AppError) as exc:
        await add_eligible_group(uuid.uuid4(), ids["pro"], db_session, admin)
    assert exc.value.code == "payment.method.not_found"

    with pytest.raises(AppError) as exc:
        await add_eligible_group(ids["open"], uuid.uuid4(), db_session, admin)
    assert exc.value.code == "price_group.not_found"
