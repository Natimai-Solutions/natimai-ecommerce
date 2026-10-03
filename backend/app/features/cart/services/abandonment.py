"""Abandoned carts (Z3): find them, remind once, report to the back office.

A cart is *abandoned* when it is still open (never checked out, active), has
at least one active line, and its last activity is older than
``CART_ABANDONMENT_REMINDER_DELAY_HOURS`` but younger than
``CART_ABANDONMENT_MAX_AGE_DAYS``. The hourly sweep publishes one
``cart.abandoned`` outbox event per cart and stamps
``abandonment_reminded_at`` in the same transaction, so a cart is reminded
once whatever the number of ticks. The e-mail itself is sent by the outbox
handler, which re-checks the cart and the customer's marketing opt-out.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import exists, func
from sqlmodel import col, or_, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.cart.models.cart import Cart, CartItem
from app.features.product.models.product import Product
from app.features.user.crud.user_preference import get_preference_for_user
from app.features.user.models.user import User
from app.outbox.registry import outbox_registry

logger = logging.getLogger(__name__)

EVENT_CART_ABANDONED = "cart.abandoned"
#: Carts handled per sweep; the next tick takes the rest.
SWEEP_BATCH_SIZE = 200


def _now() -> datetime:
    return datetime.now(UTC)


def _utc(value: datetime) -> datetime:
    """Aware UTC, as stored in Postgres (timestamptz); a naive value is read as UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def open_cart_conditions() -> list[Any]:
    """SQL: a cart that could still turn into an order."""
    return [
        col(Cart.is_active).is_(True),
        col(Cart.is_admin_active).is_(True),
        col(Cart.is_checked_out).is_(False),
        exists().where(
            col(CartItem.cart_id) == col(Cart.id),
            col(CartItem.is_active).is_(True),
        ),
    ]


def abandoned_carts_statement(
    *, now: datetime, delay_hours: int, max_age_days: int, limit: int
) -> Any:
    """Open carts due for their (single) reminder, oldest activity first."""
    newest = _utc(now - timedelta(hours=delay_hours))
    oldest = _utc(now - timedelta(days=max_age_days))
    return (
        select(Cart)
        .where(
            *open_cart_conditions(),
            # A visitor's cart can only be reminded once they typed an e-mail.
            or_(col(Cart.user_id).is_not(None), col(Cart.guest_email).is_not(None)),
            col(Cart.abandonment_reminded_at).is_(None),
            col(Cart.last_activity_at).is_not(None),
            col(Cart.last_activity_at) <= newest,
            col(Cart.last_activity_at) >= oldest,
        )
        .order_by(col(Cart.last_activity_at).asc())
        .limit(limit)
    )


async def cart_lines_payload(
    session: AsyncSession, cart_id: uuid.UUID
) -> list[dict[str, Any]]:
    """Lines of a cart with what the e-mail shows (name, image, price)."""
    rows = await session.exec(
        select(CartItem, Product)
        .join(Product, col(Product.id) == col(CartItem.product_id))
        .where(col(CartItem.cart_id) == cart_id, col(CartItem.is_active).is_(True))
        .order_by(col(CartItem.created_at).asc())
    )
    lines: list[dict[str, Any]] = []
    for item, product in rows.all():
        lines.append(
            {
                "product_id": str(product.id),
                "name": product.name,
                "quantity": int(item.quantity),
                "unit_price": str(item.unit_price),
                "line_total": str(Decimal(item.unit_price) * item.quantity),
                "image_url": product.image_url or product.supplier_image_url,
            }
        )
    return lines


async def marketing_emails_allowed(
    session: AsyncSession, user_id: uuid.UUID | None
) -> bool:
    """The customer's opt-out; no preference row means the default (allowed).

    A visitor (no account) has no preference row: the e-mail they typed in a
    form is the only consent there is, and the reminder honours it.
    """
    if user_id is None:
        return True
    preference = await get_preference_for_user(session, user_id=user_id)
    return preference is None or bool(preference.marketing_email_enabled)


async def remind_abandoned_carts(
    session: AsyncSession, *, now: datetime | None = None
) -> dict[str, int]:
    """One sweep: publish ``cart.abandoned`` for each due cart, stamp it.

    A customer who opted out is stamped too (nothing to send, nothing to
    re-evaluate next hour) and counted as ``skipped_opt_out``.
    """
    from app.core import runtime_settings

    values = await runtime_settings.get_many(
        [
            "cart_abandonment_reminder_delay_hours",
            "cart_abandonment_max_age_days",
        ],
        session,
    )
    delay_hours = int(values["cart_abandonment_reminder_delay_hours"])
    if delay_hours <= 0:
        return {"disabled": 1, "reminded": 0, "skipped_opt_out": 0, "scanned": 0}
    current = now or _now()
    rows = await session.exec(
        abandoned_carts_statement(
            now=current,
            delay_hours=delay_hours,
            max_age_days=int(values["cart_abandonment_max_age_days"]),
            limit=SWEEP_BATCH_SIZE,
        )
    )
    carts = list(rows.all())
    # Each cart commits on its own, which expires every loaded row: read the
    # fields now, the async session cannot lazy-load them back later.
    snapshots = [
        (
            cart,
            cart.id,
            cart.user_id,
            cart.guest_email,
            cart.currency,
            cart.total_amount,
            cart.last_activity_at,
        )
        for cart in carts
    ]
    reminded = 0
    skipped = 0
    for (
        cart,
        cart_id,
        user_id,
        guest_email,
        currency,
        total_amount,
        last_activity,
    ) in snapshots:
        cart.abandonment_reminded_at = _utc(current)
        session.add(cart)
        if not await marketing_emails_allowed(session, user_id):
            skipped += 1
            await session.commit()
            continue
        lines = await cart_lines_payload(session, cart_id)
        await outbox_registry.publish(
            session=session,
            event_type=EVENT_CART_ABANDONED,
            payload={
                "cart_id": str(cart_id),
                "user_id": str(user_id) if user_id else None,
                # A visitor's cart: the address they typed (R8 / U9).
                "email": None if user_id else guest_email,
                "currency": currency,
                "total_amount": str(total_amount),
                "items": lines,
                "last_activity_at": last_activity.isoformat()
                if last_activity
                else None,
            },
            correlation_id=cart_id,
        )
        await session.commit()
        reminded += 1
        logger.info("Abandoned cart %s of user %s: reminder queued", cart_id, user_id)
    return {"reminded": reminded, "skipped_opt_out": skipped, "scanned": len(carts)}


# -- back-office view ---------------------------------------------------------


async def open_carts_overview(
    session: AsyncSession, *, skip: int = 0, limit: int = 50
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Open carts with their owner, for the « paniers abandonnés » screen.

    Returns the page (most recent activity first) and three counters: open
    carts, reminded ones, and reminded carts that were checked out since
    (« récupérés » — the only number that says whether the reminder works).
    """
    page_rows = await session.exec(
        select(Cart, User)
        .outerjoin(User, col(User.id) == col(Cart.user_id))
        .where(*open_cart_conditions())
        .order_by(col(Cart.last_activity_at).desc().nulls_last())
        .offset(skip)
        .limit(limit)
    )
    page: list[dict[str, Any]] = []
    for cart, user in page_rows.all():
        lines = await cart_lines_payload(session, cart.id)
        page.append(
            {
                "cart_id": str(cart.id),
                "user_id": str(user.id) if user else None,
                # A visitor's cart (R8 / U9): the e-mail they typed, if any.
                "guest": user is None,
                "user_email": user.email if user else cart.guest_email,
                "user_name": user.full_name if user else None,
                "currency": cart.currency,
                "total_amount": str(cart.total_amount),
                "items_count": sum(line["quantity"] for line in lines),
                "items": lines,
                "last_activity_at": (
                    cart.last_activity_at.isoformat() if cart.last_activity_at else None
                ),
                "reminded_at": (
                    cart.abandonment_reminded_at.isoformat()
                    if cart.abandonment_reminded_at
                    else None
                ),
            }
        )

    async def _count(*conditions: Any) -> int:
        value = (
            await session.exec(select(func.count(col(Cart.id))).where(*conditions))
        ).one()
        return int(value)

    return page, {
        "open": await _count(*open_cart_conditions()),
        "reminded": await _count(col(Cart.abandonment_reminded_at).is_not(None)),
        "recovered": await _count(
            col(Cart.abandonment_reminded_at).is_not(None),
            col(Cart.is_checked_out).is_(True),
        ),
    }
