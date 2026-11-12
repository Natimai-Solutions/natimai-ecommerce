"""R8 / U8 — data export and erasure of a customer account (real DB)."""

from __future__ import annotations

import datetime
import json
import uuid
from decimal import Decimal
from typing import Any, cast

import pytest
from fastapi import Response
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.users_me import (
    MyAccountDeletion,
    MyPasswordChange,
    change_my_password,
    delete_my_account,
    export_my_data,
)
from app.core.errors import AppError
from app.features.cart.models.cart import Cart, CartItem
from app.features.order.models.order import Order
from app.features.order.models.order_status import OrderStatus
from app.features.product.models.product import Product
from app.features.product.models.stock_alert import StockAlert
from app.features.user.models.address import Address
from app.features.user.models.oauth_link import UserOAuthLink
from app.features.user.models.refresh_token import UserRefreshToken
from app.features.user.models.user import User
from app.features.user.models.user_preference import UserPreference
from app.features.user.models.wishlist import Wishlist, WishlistItem
from app.features.user.services.privacy import ANONYMISED_DOMAIN, erase_account


def _request() -> Any:
    from types import SimpleNamespace

    return SimpleNamespace(
        headers={"user-agent": "pytest"},
        client=SimpleNamespace(host="10.0.0.1"),
        url=SimpleNamespace(path="/api/v1/users/me/delete"),
    )


async def _user(session: AsyncSession, *, superuser: bool = False) -> User:
    from app.core.security import get_password_hash

    user = User(
        email=f"client+{uuid.uuid4().hex[:8]}@test.local",
        full_name="Hina Teriitahi",
        phone="+689 87 12 34 56",
        is_active=True,
        is_verified=True,
        is_superuser=superuser,
        hashed_password=get_password_hash("mon-mot-de-passe"),
    )
    session.add(user)
    await session.flush()
    return user


async def _seed(session: AsyncSession, user: User, *, order_status: str) -> uuid.UUID:
    status = OrderStatus(name=order_status)
    product = Product(name="Clavier", base_price=Decimal("1000"))
    session.add_all([status, product])
    await session.flush()
    order = Order(
        user_id=user.id,
        order_status_id=status.id,
        total_amount=Decimal("1000"),
        shipping_address="Hina Teriitahi, Papeete",
    )
    wishlist = Wishlist(user_id=user.id, name="Favoris")
    cart = Cart(user_id=user.id, currency="XPF")
    session.add_all(
        [
            order,
            wishlist,
            cart,
            Address(
                user_id=user.id,
                street="1 rue de la Plage",
                city="Papeete",
                postal_code="98714",
                country="PF",
                type="shipping",
            ),
            UserPreference(user_id=user.id, locale="fr"),
            StockAlert(product_id=product.id, user_id=user.id, email=user.email),
            UserRefreshToken(
                user_id=user.id,
                jti=uuid.uuid4().hex,
                expires_at=datetime.datetime.now(datetime.UTC)
                + datetime.timedelta(days=1),
            ),
        ]
    )
    await session.flush()
    session.add_all(
        [
            WishlistItem(wishlist_id=wishlist.id, product_id=product.id),
            CartItem(
                cart_id=cart.id,
                product_id=product.id,
                quantity=1,
                unit_price=Decimal("1000"),
            ),
        ]
    )
    order_id = order.id
    await session.commit()
    await session.refresh(user)
    return order_id


@pytest.mark.asyncio
async def test_export_holds_the_account_without_secrets(
    db_session: AsyncSession,
) -> None:
    user = await _user(db_session)
    await _seed(db_session, user, order_status="Delivered")

    response = await export_my_data(db_session, user)
    assert response.media_type == "application/json"
    assert "attachment" in response.headers["content-disposition"]
    payload = json.loads(bytes(response.body))

    assert payload["profile"]["email"] == user.email
    assert payload["profile"]["full_name"] == "Hina Teriitahi"
    assert len(payload["orders"]) == 1
    assert payload["orders"][0]["shipping_address"] == "Hina Teriitahi, Papeete"
    assert len(payload["addresses"]) == 1 and len(payload["preferences"]) == 1
    assert len(payload["wishlists"]) == 1 and len(payload["wishlists"][0]["items"]) == 1
    assert len(payload["stock_alerts"]) == 1
    text = json.dumps(payload)
    assert "hashed_password" not in text and "totp" not in text


@pytest.mark.asyncio
async def test_erasure_refuses_while_an_order_runs(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    await _seed(db_session, user, order_status="Paid")

    with pytest.raises(AppError) as blocked:
        await erase_account(db_session, user)
    assert blocked.value.code == "account.delete.open_orders"

    admin = await _user(db_session, superuser=True)
    await db_session.commit()
    await db_session.refresh(admin)
    with pytest.raises(AppError) as refused:
        await erase_account(db_session, admin)
    assert refused.value.code == "account.delete.superuser"


@pytest.mark.asyncio
async def test_deletion_route_checks_then_anonymises(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    order_id = await _seed(db_session, user, order_status="Delivered")
    user_id, email = user.id, user.email

    with pytest.raises(AppError) as mismatch:
        await delete_my_account(
            MyAccountDeletion(
                confirmation="autre@test.local", password="mon-mot-de-passe"
            ),
            _request(),
            Response(),
            db_session,
            user,
        )
    assert mismatch.value.code == "account.delete.confirmation_mismatch"

    with pytest.raises(AppError) as wrong:
        await delete_my_account(
            MyAccountDeletion(confirmation=email, password="pas-le-bon"),
            _request(),
            Response(),
            db_session,
            user,
        )
    assert wrong.value.code == "user.password.invalid_current"

    await delete_my_account(
        MyAccountDeletion(confirmation=email.upper(), password="mon-mot-de-passe"),
        _request(),
        Response(),
        db_session,
        user,
    )

    db_session.expire_all()
    shell = await db_session.get(User, user_id)
    assert shell is not None
    assert shell.email.endswith(f"@{ANONYMISED_DOMAIN}") and shell.email != email
    assert shell.full_name is None and shell.phone is None
    assert shell.is_active is False and shell.is_verified is False

    async def count(model: Any, *conds: Any) -> int:
        return len((await db_session.exec(select(model).where(*conds))).all())

    assert await count(Address, col(Address.user_id) == user_id) == 0
    assert await count(UserPreference, col(UserPreference.user_id) == user_id) == 0
    assert await count(Wishlist, col(Wishlist.user_id) == user_id) == 0
    assert await count(WishlistItem) == 0
    assert await count(Cart, col(Cart.user_id) == user_id) == 0
    assert await count(CartItem) == 0
    # The order stays for the books, the alert is cancelled and scrubbed.
    order = await db_session.get(Order, order_id)
    assert order is not None and order.user_id == user_id
    alert = (
        await db_session.exec(
            select(StockAlert).where(col(StockAlert.user_id) == user_id)
        )
    ).one()
    assert alert.status == "cancelled" and alert.email == shell.email
    tokens = (
        await db_session.exec(
            select(UserRefreshToken).where(col(UserRefreshToken.user_id) == user_id)
        )
    ).all()
    assert tokens and all(t.revoked_at is not None for t in tokens)
    _ = cast(Any, None)


@pytest.mark.asyncio
async def test_an_account_without_password_needs_a_recent_sign_in_to_be_erased(
    db_session: AsyncSession,
) -> None:
    """Audit 2026-11: a Google / Microsoft account was erased with no proof at
    all — a stolen session, kept alive by its refresh cookie, sufficed."""
    user = await _user(db_session)
    user_id, email = user.id, user.email
    db_session.add(
        UserOAuthLink(
            user_id=user_id,
            provider="google",
            provider_user_id=uuid.uuid4().hex,
            email_at_link=email,
        )
    )
    user.last_login = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=3)
    await db_session.commit()
    await db_session.refresh(user)

    with pytest.raises(AppError) as stale:
        await delete_my_account(
            MyAccountDeletion(confirmation=email, password=None),
            _request(),
            Response(),
            db_session,
            user,
        )
    assert stale.value.code == "account.delete.reauth_required"

    user.last_login = datetime.datetime.now(datetime.UTC)
    await db_session.commit()
    await db_session.refresh(user)
    await delete_my_account(
        MyAccountDeletion(confirmation=email, password=None),
        _request(),
        Response(),
        db_session,
        user,
    )
    db_session.expire_all()
    shell = await db_session.get(User, user_id)
    assert shell is not None and shell.is_active is False


@pytest.mark.asyncio
async def test_a_password_change_voids_a_pending_reset_link(
    db_session: AsyncSession,
) -> None:
    """Audit 2026-11: a reset link still valid undid the change made since."""
    user = await _user(db_session)
    user_id = user.id
    user.password_reset_token = "pending-link-hash"
    user.password_reset_token_expires = datetime.datetime.now(
        datetime.UTC
    ) + datetime.timedelta(minutes=30)
    await db_session.commit()
    await db_session.refresh(user)

    await change_my_password(
        MyPasswordChange(
            current_password="mon-mot-de-passe", new_password="un-autre-secret"
        ),
        db_session,
        user,
    )
    db_session.expire_all()
    refreshed = await db_session.get(User, user_id)
    assert refreshed is not None
    assert refreshed.password_reset_token is None
    assert refreshed.password_reset_token_expires is None
