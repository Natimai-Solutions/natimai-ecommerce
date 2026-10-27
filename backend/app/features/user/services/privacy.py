"""Customer data rights in self-service (R8 / U8): export and erasure.

The privacy page promises access, rectification and erasure; this module is
what « Mon compte → Profil et sécurité » calls for the first and the last.

* :func:`export_account` gathers every row the shop holds about the customer
  (profile, preferences, addresses, orders and lines, payments, quotes,
  alerts, favourites, reviews, group requests, notifications, sign-in
  providers) as plain JSON. Credentials and secrets are never exported.
* :func:`erase_account` removes what only served the account (addresses,
  favourites, preferences, notifications, open carts, sign-in providers,
  reviews), scrubs the personal data of what must stay for the shop's books
  (quote requests, stock alerts) and turns the user row into an anonymous
  shell: orders, invoices and payments reference it and are kept for the
  legal retention period, without a name, e-mail, phone or credential.
  An account with an order still in progress cannot be erased.
"""

from __future__ import annotations

import secrets
import uuid
from typing import Any

from sqlalchemy import delete as sa_delete
from sqlalchemy import update as sa_update
from sqlmodel import SQLModel, col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.datetimes import utcnow
from app.core.errors import AppError
from app.core.security import get_password_hash, new_security_stamp
from app.features.cart.models.cart import Cart, CartItem
from app.features.cart.models.quote_request import QuoteRequest
from app.features.notification.models.email_log import EmailLog
from app.features.order.models.order import Order
from app.features.order.models.order_line import OrderLine
from app.features.order.models.order_status import OrderStatus
from app.features.payment.models.payment import Payment
from app.features.product.models.stock_alert import StockAlert
from app.features.user.crud.refresh_token import crud_user_refresh_token
from app.features.user.models.address import Address
from app.features.user.models.group_upgrade_request import GroupUpgradeRequest
from app.features.user.models.notification import UserNotification
from app.features.user.models.oauth_link import UserOAuthLink
from app.features.user.models.review import Review
from app.features.user.models.user import User
from app.features.user.models.user_preference import UserPreference
from app.features.user.models.wishlist import Wishlist, WishlistItem

EXPORT_FORMAT = "natimai-account-export/1"

#: Orders in these statuses are over: nothing left to deliver, pay or refund.
CLOSED_ORDER_STATUSES: frozenset[str] = frozenset(
    {"Delivered", "Cancelled", "Refunded", "PaymentFailed"}
)

#: Never exported: credentials, secrets and internal bookkeeping.
_PRIVATE_FIELDS: frozenset[str] = frozenset(
    {
        "hashed_password",
        "password_reset_token",
        "password_reset_token_expires",
        "email_verification_token",
        "email_verification_token_expires",
        "totp_secret_encrypted",
        "totp_recovery_hashes",
        "totp_last_step",
        "failed_login_attempts",
        "locked_until",
        "created_by_id",
        "modify_by_id",
        "is_admin_active",
        "admin_comment",
    }
)

ANONYMISED_DOMAIN = "anonymised.invalid"


def _dump(row: SQLModel) -> dict[str, Any]:
    return row.model_dump(mode="json", exclude=set(_PRIVATE_FIELDS))


async def _rows(session: AsyncSession, statement: Any) -> list[dict[str, Any]]:
    return [_dump(row) for row in (await session.exec(statement)).all()]


def anonymised_email(user_id: uuid.UUID) -> str:
    return f"deleted-{user_id.hex[:12]}@{ANONYMISED_DOMAIN}"


async def export_account(session: AsyncSession, user: User) -> dict[str, Any]:
    """Everything the shop holds about the customer, as JSON-ready data."""
    uid = user.id
    orders = (
        await session.exec(
            select(Order)
            .where(col(Order.user_id) == uid)
            .order_by(col(Order.created_at))
        )
    ).all()
    order_ids = [order.id for order in orders]
    lines_by_order: dict[uuid.UUID, list[dict[str, Any]]] = {}
    if order_ids:
        for line in (
            await session.exec(
                select(OrderLine).where(col(OrderLine.order_id).in_(order_ids))
            )
        ).all():
            lines_by_order.setdefault(line.order_id, []).append(_dump(line))
    wishlists = (
        await session.exec(select(Wishlist).where(col(Wishlist.user_id) == uid))
    ).all()
    wishlist_ids = [w.id for w in wishlists]
    items_by_wishlist: dict[uuid.UUID, list[dict[str, Any]]] = {}
    if wishlist_ids:
        for item in (
            await session.exec(
                select(WishlistItem).where(
                    col(WishlistItem.wishlist_id).in_(wishlist_ids)
                )
            )
        ).all():
            items_by_wishlist.setdefault(item.wishlist_id, []).append(_dump(item))

    return {
        "format": EXPORT_FORMAT,
        "exported_at": utcnow().isoformat(),
        "profile": {
            "id": str(uid),
            "email": user.email,
            "full_name": user.full_name,
            "phone": user.phone,
            "is_verified": bool(user.is_verified),
            "two_factor_enabled": bool(getattr(user, "totp_enabled", False)),
            "created_at": _iso(getattr(user, "created_at", None)),
            "last_login": _iso(getattr(user, "last_login", None)),
            "price_group_id": _str(getattr(user, "price_group_id", None)),
        },
        "preferences": await _rows(
            session, select(UserPreference).where(col(UserPreference.user_id) == uid)
        ),
        "addresses": await _rows(
            session, select(Address).where(col(Address.user_id) == uid)
        ),
        "orders": [
            {**_dump(order), "lines": lines_by_order.get(order.id, [])}
            for order in orders
        ],
        "payments": await _rows(
            session,
            select(Payment)
            .where(col(Payment.user_id) == uid)
            .order_by(col(Payment.created_at)),
        ),
        "quote_requests": await _rows(
            session,
            select(QuoteRequest)
            .where(col(QuoteRequest.user_id) == uid)
            .order_by(col(QuoteRequest.created_at)),
        ),
        "stock_alerts": await _rows(
            session, select(StockAlert).where(col(StockAlert.user_id) == uid)
        ),
        "wishlists": [
            {**_dump(w), "items": items_by_wishlist.get(w.id, [])} for w in wishlists
        ],
        "reviews": await _rows(
            session, select(Review).where(col(Review.user_id) == uid)
        ),
        "group_upgrade_requests": await _rows(
            session,
            select(GroupUpgradeRequest).where(col(GroupUpgradeRequest.user_id) == uid),
        ),
        "notifications": await _rows(
            session,
            select(UserNotification).where(col(UserNotification.user_id) == uid),
        ),
        "sign_in_providers": [
            {
                "provider": link.provider,
                "email_at_link": link.email_at_link,
                "created_at": _iso(getattr(link, "created_at", None)),
            }
            for link in (
                await session.exec(
                    select(UserOAuthLink).where(col(UserOAuthLink.user_id) == uid)
                )
            ).all()
        ],
    }


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _str(value: Any) -> str | None:
    return str(value) if value is not None else None


async def open_orders_count(session: AsyncSession, user_id: uuid.UUID) -> int:
    """Orders of the customer still running (not delivered, cancelled, refunded)."""
    statement = (
        select(func.count())
        .select_from(Order)
        .join(OrderStatus, col(OrderStatus.id) == col(Order.order_status_id))
        .where(
            col(Order.user_id) == user_id,
            col(Order.is_active).is_(True),
            col(OrderStatus.name).not_in(CLOSED_ORDER_STATUSES),
        )
    )
    return int((await session.exec(statement)).one())


async def erase_account(session: AsyncSession, user: User) -> None:
    """Erase the customer's personal data; see the module docstring.

    Raises ``account.delete.superuser`` (403) for an administrator (removed
    from the back-office instead) and ``account.delete.open_orders`` (409)
    while an order is in progress.
    """
    if user.is_superuser:
        raise AppError(
            code="account.delete.superuser",
            status_code=403,
            message="Un compte administrateur se supprime depuis le back-office.",
        )
    uid = user.id
    running = await open_orders_count(session, uid)
    if running:
        raise AppError(
            code="account.delete.open_orders",
            status_code=409,
            message=(
                "Une commande est encore en cours : le compte pourra être "
                "supprimé une fois qu'elle sera livrée ou annulée."
            ),
            details={"open_orders": running},
        )

    # What only served the account.
    wishlist_ids = select(Wishlist.id).where(col(Wishlist.user_id) == uid)
    await session.execute(
        sa_delete(WishlistItem).where(col(WishlistItem.wishlist_id).in_(wishlist_ids))
    )
    for model in (
        Wishlist,
        Address,
        UserPreference,
        UserNotification,
        UserOAuthLink,
        Review,
        GroupUpgradeRequest,
    ):
        await session.execute(sa_delete(model).where(col(model.user_id) == uid))
    # Carts never ordered (an ordered cart documents the order and stays).
    open_cart_ids = select(Cart.id).where(
        col(Cart.user_id) == uid, col(Cart.is_checked_out).is_not(True)
    )
    await session.execute(
        sa_delete(CartItem).where(col(CartItem.cart_id).in_(open_cart_ids))
    )
    await session.execute(
        sa_delete(Cart).where(
            col(Cart.user_id) == uid, col(Cart.is_checked_out).is_not(True)
        )
    )
    # What stays for the shop's books, without the person.
    placeholder = anonymised_email(uid)
    await session.execute(
        sa_update(StockAlert)
        .where(col(StockAlert.user_id) == uid)
        .values(status="cancelled", email=placeholder)
    )
    await session.execute(
        sa_update(QuoteRequest)
        .where(col(QuoteRequest.user_id) == uid)
        .values(
            email=placeholder,
            phone=None,
            full_name=None,
            shipping_address=None,
            notes=None,
        )
    )
    # The e-mails sent to the person: address and bodies are personal data.
    if user.email:
        await session.execute(
            sa_delete(EmailLog).where(
                func.lower(col(EmailLog.recipient)) == user.email.lower()
            )
        )
    await crud_user_refresh_token.revoke_all_active_for_user(
        session, user_id=uid, reason="account_deleted"
    )
    # The user row: an anonymous shell nobody can sign into.
    user.email = placeholder
    user.full_name = None
    user.phone = None
    user.hashed_password = get_password_hash(secrets.token_urlsafe(32))
    user.security_stamp = new_security_stamp()
    user.is_active = False
    user.is_verified = False
    user.password_reset_token = None
    user.password_reset_token_expires = None
    user.email_verification_token = None
    user.email_verification_token_expires = None
    user.totp_secret_encrypted = None
    user.totp_enabled = False
    user.totp_enabled_at = None
    user.totp_recovery_hashes = None
    user.locked_until = None
    session.add(user)
    await session.commit()


__all__ = [
    "ANONYMISED_DOMAIN",
    "CLOSED_ORDER_STATUSES",
    "EXPORT_FORMAT",
    "anonymised_email",
    "erase_account",
    "export_account",
    "open_orders_count",
]
