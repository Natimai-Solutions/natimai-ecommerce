"""Integration tests (real DB): the « Mon compte » additions of the storefront
redesign — profile read / edit, password change, and the single-order detail
with the payment method and product pictures on the lines."""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

import pytest
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.orders_me import get_my_order, get_my_order_lines
from app.api.routes.users_me import (
    MyPasswordChange,
    MyProfileUpdate,
    change_my_password,
    get_my_profile,
    update_my_profile,
)
from app.core.errors import AppError
from app.core.security import get_password_hash, verify_password
from app.features.order.models.order import Order
from app.features.order.models.order_line import OrderLine
from app.features.order.models.order_status import OrderStatus
from app.features.payment.models.payment import Payment
from app.features.payment.models.payment_method import PaymentMethod
from app.features.product.models.product import Product
from app.features.user.models.refresh_token import UserRefreshToken
from app.features.user.models.user import User


async def _user(
    db_session: AsyncSession, password: str = "ancien-mot-de-passe"
) -> User:
    user = User(
        email=f"client+{uuid.uuid4().hex[:8]}@test.local",
        full_name="Hina Teriitahi",
        is_active=True,
        is_verified=True,
        hashed_password=get_password_hash(password),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_profile_read_and_edit(db_session: AsyncSession) -> None:
    user = await _user(db_session)

    profile = await get_my_profile(user)
    assert profile.email == user.email and profile.full_name == "Hina Teriitahi"
    assert profile.phone is None and profile.is_verified

    updated = await update_my_profile(
        MyProfileUpdate(full_name="  Hina T. ", phone="+689 87 12 34 56"),
        db_session,
        user,
    )
    assert updated.full_name == "Hina T." and updated.phone == "+689 87 12 34 56"

    # A field left out is unchanged; an empty string clears it.
    cleared = await update_my_profile(MyProfileUpdate(phone=""), db_session, user)
    assert cleared.full_name == "Hina T." and cleared.phone is None


@pytest.mark.asyncio
async def test_password_change_checks_the_current_one_and_closes_sessions(
    db_session: AsyncSession,
) -> None:
    user = await _user(db_session, password="ancien-mot-de-passe")
    db_session.add(
        UserRefreshToken(
            user_id=user.id,
            jti=uuid.uuid4().hex,
            expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1),
        )
    )
    await db_session.commit()
    await db_session.refresh(user)

    with pytest.raises(AppError) as wrong:
        await change_my_password(
            MyPasswordChange(
                current_password="pas-le-bon", new_password="nouveau-mot-de-passe"
            ),
            db_session,
            user,
        )
    assert wrong.value.code == "user.password.invalid_current"

    with pytest.raises(AppError) as same:
        await change_my_password(
            MyPasswordChange(
                current_password="ancien-mot-de-passe",
                new_password="ancien-mot-de-passe",
            ),
            db_session,
            user,
        )
    assert same.value.code == "user.password.unchanged"

    await change_my_password(
        MyPasswordChange(
            current_password="ancien-mot-de-passe",
            new_password="nouveau-mot-de-passe",
        ),
        db_session,
        user,
    )
    await db_session.refresh(user)
    assert user.hashed_password is not None
    assert verify_password("nouveau-mot-de-passe", user.hashed_password)
    tokens = (
        await db_session.exec(
            select(UserRefreshToken).where(col(UserRefreshToken.user_id) == user.id)
        )
    ).all()
    assert tokens and all(token.revoked_at is not None for token in tokens)


@pytest.mark.asyncio
async def test_order_detail_is_owned_and_carries_payment_method_and_pictures(
    db_session: AsyncSession,
) -> None:
    buyer = await _user(db_session)
    stranger = await _user(db_session)
    await db_session.refresh(buyer)
    status = OrderStatus(name="Paid")
    method = PaymentMethod(name="Virement bancaire", provider_code="manual_transfer")
    shown = Product(
        name="Portable 14 pouces",
        manufacturer="Lenovo",
        supplier_image_url="https://images.example/portable.jpg",
    )
    gone = Product(name="Ancien modèle", is_active=False)
    db_session.add_all([status, method, shown, gone])
    await db_session.flush()
    order = Order(
        user_id=buyer.id,
        order_status_id=status.id,
        order_number=f"CMD-{uuid.uuid4().hex[:6]}",
        currency="XPF",
        subtotal_amount=Decimal("150000"),
        total_amount=Decimal("150000"),
        shipping_address="12 rue des Remparts, 98714 Papeete",
    )
    db_session.add(order)
    await db_session.flush()
    order_id = order.id
    db_session.add_all(
        [
            OrderLine(
                order_id=order.id,
                product_id=shown.id,
                quantity=1,
                unit_price=Decimal("120000"),
            ),
            OrderLine(
                order_id=order.id,
                product_id=gone.id,
                quantity=2,
                unit_price=Decimal("15000"),
            ),
            Payment(
                order_id=order.id,
                user_id=buyer.id,
                payment_method_id=method.id,
                amount=Decimal("150000"),
                currency="XPF",
                provider_code="manual_transfer",
            ),
        ]
    )
    await db_session.commit()
    await db_session.refresh(buyer)
    await db_session.refresh(stranger)

    detail = await get_my_order(order_id, db_session, buyer)
    assert detail.order_status_name == "Paid"
    assert detail.payment_method_name == "Virement bancaire"
    assert detail.shipping_address == "12 rue des Remparts, 98714 Papeete"

    lines = {
        line.product_name: line
        for line in await get_my_order_lines(order_id, db_session, buyer)
    }
    assert (
        lines["Portable 14 pouces"].image_url == "https://images.example/portable.jpg"
    )
    assert lines["Portable 14 pouces"].manufacturer == "Lenovo"
    assert lines["Portable 14 pouces"].product_available is True
    assert lines["Ancien modèle"].product_available is False

    with pytest.raises(AppError) as foreign:
        await get_my_order(order_id, db_session, stranger)
    assert foreign.value.code == "order.not_found"
