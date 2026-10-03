"""Loyalty points: rules, balance, earning on a paid order, revocation on a
refund, conversion into store credit (R8 / confort — commerce)."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal
from typing import Any

from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core import runtime_settings
from app.core.config import settings
from app.core.errors import AppError
from app.features.order.models.order import Order
from app.features.order.models.order_line import OrderLine
from app.features.payment.models.loyalty import (
    LoyaltyAccount,
    LoyaltyEntry,
    LoyaltyEntryPublic,
    LoyaltyRules,
)
from app.features.payment.services import store_credit
from app.features.product.models.product import Product
from app.utils.money import quantize_amount

logger = logging.getLogger(__name__)

SETTING_ENABLED = "loyalty_enabled"
SETTING_AMOUNT_PER_POINT = "loyalty_amount_per_point"
SETTING_POINT_VALUE = "loyalty_point_value"
SETTING_MIN_CONVERT = "loyalty_min_points_to_convert"


async def rules(session: AsyncSession) -> LoyaltyRules:
    """The programme's parameters as set in the back-office."""
    amount_per_point = Decimal(
        str(await runtime_settings.get(SETTING_AMOUNT_PER_POINT, session) or 0)
    )
    point_value = Decimal(
        str(await runtime_settings.get(SETTING_POINT_VALUE, session) or 0)
    )
    return LoyaltyRules(
        enabled=bool(await runtime_settings.get(SETTING_ENABLED, session))
        and amount_per_point > 0
        and point_value > 0,
        currency=settings.REFERENCE_CURRENCY,
        amount_per_point=amount_per_point,
        point_value=point_value,
        min_points_to_convert=max(
            1, int(await runtime_settings.get(SETTING_MIN_CONVERT, session) or 1)
        ),
    )


async def balance(session: AsyncSession, user_id: uuid.UUID) -> int:
    total = (
        await session.exec(
            select(func.coalesce(func.sum(col(LoyaltyEntry.points)), 0)).where(
                col(LoyaltyEntry.user_id) == user_id,
                col(LoyaltyEntry.is_active).is_(True),
            )
        )
    ).one()
    return int(total)


async def entries(session: AsyncSession, user_id: uuid.UUID) -> list[LoyaltyEntry]:
    return list(
        (
            await session.exec(
                select(LoyaltyEntry)
                .where(
                    col(LoyaltyEntry.user_id) == user_id,
                    col(LoyaltyEntry.is_active).is_(True),
                )
                .order_by(col(LoyaltyEntry.created_at).desc())
            )
        ).all()
    )


async def account(session: AsyncSession, user_id: uuid.UUID) -> LoyaltyAccount:
    current = await rules(session)
    points = await balance(session, user_id)
    return LoyaltyAccount(
        user_id=user_id,
        points=points,
        credit_value=quantize_amount(
            Decimal(points) * current.point_value, current.currency
        ),
        rules=current,
        entries=[
            LoyaltyEntryPublic.model_validate(e)
            for e in await entries(session, user_id)
        ],
    )


def _add(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    points: int,
    kind: str,
    reason: str | None,
    order_id: uuid.UUID | None = None,
    created_by_id: uuid.UUID | None = None,
    store_credit_entry_id: uuid.UUID | None = None,
) -> LoyaltyEntry:
    entry = LoyaltyEntry(
        user_id=user_id,
        points=points,
        kind=kind,
        reason=reason,
        order_id=order_id,
        created_by_id=created_by_id,
        store_credit_entry_id=store_credit_entry_id,
        # Set here: the ledger is read newest first, and nothing else stamps it.
        created_at=datetime.now(UTC),
    )
    session.add(entry)
    return entry


async def _eligible_amount(session: AsyncSession, order: Order) -> Decimal:
    """What the order earns points on: the goods, gift cards excluded (their
    value earns when it is spent), shipping and payment fees excluded."""
    lines = (
        await session.exec(select(OrderLine).where(col(OrderLine.order_id) == order.id))
    ).all()
    if not lines:
        return Decimal(0)
    gift_products: set[uuid.UUID] = set(
        (
            await session.exec(
                select(Product.id).where(
                    col(Product.id).in_({line.product_id for line in lines}),
                    col(Product.gift_card_amount).is_not(None),
                )
            )
        ).all()
    )
    total = Decimal(0)
    for line in lines:
        if line.product_id in gift_products:
            continue
        total += Decimal(line.unit_price) * line.quantity - Decimal(
            line.discount_amount or 0
        )
    return max(total, Decimal(0))


async def earn_for_order(session: AsyncSession, *, order_id: uuid.UUID) -> int:
    """Credit the order's points once; returns the points earned (0 when the
    programme is off, the order earns nothing, or it already did). Flushes,
    no commit."""
    current = await rules(session)
    if not current.enabled:
        return 0
    order = await session.get(Order, order_id)
    if order is None:
        return 0
    already = (
        await session.exec(
            select(func.count())
            .select_from(LoyaltyEntry)
            .where(
                col(LoyaltyEntry.order_id) == order_id,
                col(LoyaltyEntry.kind) == "earn",
            )
        )
    ).one()
    if int(already) > 0:
        return 0
    amount = await _eligible_amount(session, order)
    points = int((amount / current.amount_per_point).to_integral_value(ROUND_DOWN))
    if points <= 0:
        return 0
    _add(
        session,
        user_id=order.user_id,
        points=points,
        kind="earn",
        reason=f"Commande {order.order_number or order.id}",
        order_id=order_id,
    )
    await session.flush()
    logger.info("Order %s: %d loyalty point(s) earned", order_id, points)
    return points


async def revoke_for_refund(
    session: AsyncSession, *, order_id: uuid.UUID, refunded: Decimal, fully: bool
) -> int:
    """Take back the order's points in proportion to the refund (all of them
    on a full refund), never below the customer's current balance. Returns
    the points revoked. Flushes, no commit."""
    order = await session.get(Order, order_id)
    if order is None:
        return 0
    earned = int(
        (
            await session.exec(
                select(func.coalesce(func.sum(col(LoyaltyEntry.points)), 0)).where(
                    col(LoyaltyEntry.order_id) == order_id,
                    col(LoyaltyEntry.kind).in_(["earn", "revoke"]),
                )
            )
        ).one()
    )
    if earned <= 0:
        return 0
    if fully or not order.total_amount or Decimal(order.total_amount) <= 0:
        share = Decimal(1)
    else:
        share = min(Decimal(1), Decimal(refunded) / Decimal(order.total_amount))
    to_revoke = int((Decimal(earned) * share).to_integral_value(ROUND_DOWN))
    to_revoke = min(to_revoke, max(0, await balance(session, order.user_id)))
    if to_revoke <= 0:
        return 0
    _add(
        session,
        user_id=order.user_id,
        points=-to_revoke,
        kind="revoke",
        reason=f"Remboursement — commande {order.order_number or order.id}",
        order_id=order_id,
    )
    await session.flush()
    return to_revoke


async def convert(
    session: AsyncSession, *, user_id: uuid.UUID, points: int
) -> LoyaltyEntry:
    """Turn ``points`` into store credit; flushes, no commit."""
    current = await rules(session)
    if not current.enabled:
        raise AppError(
            code="loyalty.disabled",
            status_code=409,
            message="Le programme de fidélité n'est pas actif",
            details={},
        )
    if points < current.min_points_to_convert:
        raise AppError(
            code="loyalty.below_minimum",
            status_code=400,
            message=f"Conversion possible à partir de {current.min_points_to_convert} points",
            details={"min_points": current.min_points_to_convert},
        )
    available = await balance(session, user_id)
    if points > available:
        raise AppError(
            code="loyalty.insufficient",
            status_code=409,
            message="Solde de points insuffisant",
            details={"available": available, "requested": points},
        )
    amount = quantize_amount(Decimal(points) * current.point_value, current.currency)
    credit = await store_credit.grant(
        session,
        user_id=user_id,
        amount=amount,
        reason=f"Conversion de {points} points de fidélité",
        currency=current.currency,
        order_id=None,
        admin=None,
    )
    entry = _add(
        session,
        user_id=user_id,
        points=-points,
        kind="convert",
        reason=f"Avoir de {amount} {current.currency}",
        store_credit_entry_id=credit.id,
    )
    await session.flush()
    return entry


async def adjust(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    points: int,
    reason: str,
    order_id: uuid.UUID | None,
    admin: Any,
) -> LoyaltyEntry:
    """Admin adjustment; a negative one cannot take the balance below zero.
    Flushes, no commit."""
    if points < 0 and await balance(session, user_id) + points < 0:
        raise AppError(
            code="loyalty.insufficient",
            status_code=409,
            message="Le solde de points ne peut pas devenir négatif",
            details={"user_id": str(user_id)},
        )
    entry = _add(
        session,
        user_id=user_id,
        points=points,
        kind="adjust",
        reason=reason.strip(),
        order_id=order_id,
        created_by_id=getattr(admin, "id", None),
    )
    await session.flush()
    return entry
