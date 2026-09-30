"""Payment methods created and edited from the admin, real database.

Two transfers to two banks, each with its own IBAN; a method's instructions
winning over its type's; a card method refusing instructions; a used method
that cannot be deleted.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.admin_payment_methods import (
    AdminPaymentMethodCreate,
    AdminPaymentMethodWrite,
    create_payment_method,
    delete_payment_method,
    list_admin_payment_methods,
    list_payment_method_types,
    update_payment_method,
)
from app.core.errors import AppError
from app.features.payment.models.payment_method import PaymentMethod
from app.features.payment.providers import ManualTransferProvider
from app.features.payment.services.payment_initiation import (
    initiate_payment_for_method,
)
from app.features.system.models.system_setting import SystemSetting
from app.features.user.models.user import User

BNP_IBAN = "Virement BNP Paribas NC — IBAN FR76 1234 5678 9012 3456 7890 123"
BDT_IBAN = "Virement Banque de Tahiti — IBAN FR76 9999 8888 7777 6666 5555 444"


async def _admin(session: AsyncSession) -> Any:
    admin = User(
        email=f"admin+{uuid.uuid4().hex[:6]}@t.local",
        is_superuser=True,
        hashed_password="x",
    )
    session.add(admin)
    await session.flush()
    snapshot = SimpleNamespace(id=admin.id, is_superuser=True)
    await session.commit()
    return snapshot


async def _customer(session: AsyncSession) -> Any:
    user = User(email=f"c+{uuid.uuid4().hex[:6]}@t.local", hashed_password="x")
    session.add(user)
    await session.flush()
    snapshot = SimpleNamespace(
        id=user.id, email=user.email, full_name=None, price_group_id=None
    )
    await session.commit()
    return snapshot


async def _pay(session: AsyncSession, method_id: uuid.UUID, user: Any) -> str | None:
    result = await initiate_payment_for_method(
        session,
        payment_method_id=method_id,
        amount=Decimal("5000"),
        currency="XPF",
        order_id=None,
        return_url=None,
        metadata=None,
        current_user=user,
    )
    instructions = result.instructions
    await session.commit()
    return instructions


def _s(session: AsyncSession) -> Any:
    return cast(Any, session)


@pytest.mark.asyncio
async def test_two_transfers_to_two_banks_each_send_their_iban(
    db_session: AsyncSession,
) -> None:
    admin = await _admin(db_session)
    user = await _customer(db_session)
    db_session.add(
        SystemSetting(key="payment_instructions_manual_transfer", value=BNP_IBAN)
    )
    await db_session.commit()

    bnp = await create_payment_method(
        AdminPaymentMethodCreate(provider_code="manual_transfer", name="Virement BNP"),
        _s(db_session),
        admin,
    )
    bdt = await create_payment_method(
        AdminPaymentMethodCreate(
            provider_code="Manual_Transfer",
            name="Virement Banque de Tahiti",
            description="  Pour les clients de la Banque de Tahiti  ",
            instructions=f"  {BDT_IBAN}  ",
            max_amount=Decimal("500000"),
        ),
        _s(db_session),
        admin,
    )
    assert bdt.provider_code == "manual_transfer"
    assert bdt.type_label == "Virement bancaire"
    assert bdt.supports_instructions is True
    assert bdt.description == "Pour les clients de la Banque de Tahiti"
    assert bdt.instructions == BDT_IBAN
    assert bdt.sort_order > bnp.sort_order

    # The method's own text wins; without one, its type's text applies.
    assert await _pay(db_session, bdt.id, user) == BDT_IBAN
    assert await _pay(db_session, bnp.id, user) == BNP_IBAN

    # Emptying the method's text falls back to the type's.
    await update_payment_method(
        bdt.id, AdminPaymentMethodWrite(instructions="   "), _s(db_session), admin
    )
    assert await _pay(db_session, bdt.id, user) == BNP_IBAN

    listed = {
        m.name: m for m in await list_admin_payment_methods(_s(db_session), admin)
    }
    assert listed["Virement BNP"].payments_count == 1
    assert listed["Virement Banque de Tahiti"].payments_count == 2
    assert listed["Virement Banque de Tahiti"].instructions is None


@pytest.mark.asyncio
async def test_edit_rename_cap_and_switch_off(db_session: AsyncSession) -> None:
    admin = await _admin(db_session)
    created = await create_payment_method(
        AdminPaymentMethodCreate(
            provider_code="manual_cash", name="Espèces", max_amount=Decimal("100000")
        ),
        _s(db_session),
        admin,
    )
    updated = await update_payment_method(
        created.id,
        AdminPaymentMethodWrite(
            name="Espèces au bureau de Papeete",
            fee=Decimal("200"),
            max_amount=None,
            sort_order=5,
            is_admin_active=False,
            deposit_allowed=False,
        ),
        _s(db_session),
        admin,
    )
    assert updated.name == "Espèces au bureau de Papeete"
    assert updated.fee == Decimal("200")
    assert updated.max_amount is None
    assert updated.sort_order == 5
    assert updated.is_admin_active is False
    assert updated.deposit_allowed is False

    # A partial edit leaves the other fields alone.
    again = await update_payment_method(
        created.id, AdminPaymentMethodWrite(description="Bureau"), _s(db_session), admin
    )
    assert again.fee == Decimal("200") and again.is_admin_active is False


@pytest.mark.asyncio
async def test_names_are_unique_and_types_must_exist(db_session: AsyncSession) -> None:
    admin = await _admin(db_session)
    await create_payment_method(
        AdminPaymentMethodCreate(provider_code="manual_check", name="Chèque"),
        _s(db_session),
        admin,
    )
    with pytest.raises(AppError) as taken:
        await create_payment_method(
            AdminPaymentMethodCreate(provider_code="manual_check", name=" chèque "),
            _s(db_session),
            admin,
        )
    assert taken.value.code == "payment.method.name_taken"

    with pytest.raises(AppError) as unknown:
        await create_payment_method(
            AdminPaymentMethodCreate(provider_code="bitcoin", name="Bitcoin"),
            _s(db_session),
            admin,
        )
    assert unknown.value.code == "payment.method.type_unknown"


@pytest.mark.asyncio
async def test_a_card_method_sends_no_instructions(db_session: AsyncSession) -> None:
    admin = await _admin(db_session)
    with pytest.raises(AppError) as refused:
        await create_payment_method(
            AdminPaymentMethodCreate(
                provider_code="payzen", name="Carte", instructions="IBAN…"
            ),
            _s(db_session),
            admin,
        )
    assert refused.value.code == "payment.method.instructions_unsupported"

    card = await create_payment_method(
        AdminPaymentMethodCreate(provider_code="payzen", name="Carte"),
        _s(db_session),
        admin,
    )
    assert card.family == "card"
    assert card.supports_instructions is False
    method = await db_session.get(PaymentMethod, card.id)
    assert method is not None and method.requires_admin_validation is False


@pytest.mark.asyncio
async def test_types_show_what_the_customer_receives_by_default(
    db_session: AsyncSession,
) -> None:
    admin = await _admin(db_session)
    db_session.add(
        SystemSetting(key="payment_instructions_manual_cash", value="Bureau, Papeete")
    )
    await db_session.commit()
    types = {t.code: t for t in await list_payment_method_types(_s(db_session), admin)}
    assert set(types) >= {
        "payzen",
        "paypal",
        "manual_cash",
        "manual_check",
        "manual_transfer",
        "po_public",
    }
    assert types["manual_cash"].fallback_instructions == "Bureau, Papeete"
    assert (
        types["manual_transfer"].fallback_instructions
        == ManualTransferProvider.instructions.strip()
    )
    assert types["paypal"].family == "wallet"
    assert types["paypal"].fallback_instructions is None
    assert types["po_public"].family == "document"


@pytest.mark.asyncio
async def test_only_an_unused_method_can_be_deleted(db_session: AsyncSession) -> None:
    admin = await _admin(db_session)
    user = await _customer(db_session)
    unused = await create_payment_method(
        AdminPaymentMethodCreate(provider_code="manual_check", name="Chèque (essai)"),
        _s(db_session),
        admin,
    )
    used = await create_payment_method(
        AdminPaymentMethodCreate(provider_code="manual_check", name="Chèque"),
        _s(db_session),
        admin,
    )
    await _pay(db_session, used.id, user)

    response = await delete_payment_method(unused.id, _s(db_session), admin)
    assert response.status_code == 204
    assert await db_session.get(PaymentMethod, unused.id) is None

    with pytest.raises(AppError) as in_use:
        await delete_payment_method(used.id, _s(db_session), admin)
    assert in_use.value.code == "payment.method.in_use"
    assert in_use.value.status_code == 409
