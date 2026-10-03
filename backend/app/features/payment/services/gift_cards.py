"""Gift cards and vouchers: issue, redeem into store credit, and the cards a
paid order entitles its buyer to (R8 / confort — commerce)."""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core import runtime_settings
from app.core.config import settings
from app.core.errors import AppError
from app.features.order.models.order import Order
from app.features.order.models.order_line import OrderLine
from app.features.payment.models.gift_card import (
    KIND_GIFT_CARD,
    KIND_VOUCHER,
    GiftCard,
    GiftCardPublic,
)
from app.features.payment.models.store_credit import StoreCreditEntry
from app.features.payment.services import store_credit
from app.features.product.models.product import Product
from app.features.user.models.user import User
from app.outbox.registry import outbox_registry
from app.utils.money import quantize_amount

logger = logging.getLogger(__name__)

EVENT_GIFT_CARDS_ISSUED = "gift_card.issued"
SETTING_VALIDITY_MONTHS = "gift_card_validity_months"

#: No 0/O, 1/I/L: a code is read over the phone or typed from a printed card.
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def generate_code() -> str:
    """``XXXX-XXXX-XXXX-XXXX`` from an unambiguous alphabet (~79 bits)."""
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(16))
    return "-".join(raw[i : i + 4] for i in range(0, 16, 4))


def normalize_code(typed: str) -> str:
    """What the customer typed → the stored form (upper case, grouped by 4)."""
    cleaned = "".join(ch for ch in typed.upper() if ch.isalnum())
    return "-".join(cleaned[i : i + 4] for i in range(0, len(cleaned), 4))


def mask_code(code: str) -> str:
    """``XXXX-XXXX-XXXX-AB7K`` → ``····-····-····-AB7K`` for ledgers and logs."""
    tail = code.rsplit("-", 1)[-1]
    return f"····-····-····-{tail}"


def state_of(card: GiftCard, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    if card.redeemed_at is not None:
        return "redeemed"
    if not card.is_active:
        return "cancelled"
    if card.expires_at is not None and card.expires_at <= now:
        return "expired"
    return "active"


def to_public(
    card: GiftCard, *, redeemed_by_email: str | None = None
) -> GiftCardPublic:
    return GiftCardPublic(
        id=card.id,
        code=card.code,
        kind=card.kind,
        amount=card.amount,
        currency=card.currency,
        recipient_email=card.recipient_email,
        note=card.note,
        expires_at=card.expires_at,
        order_id=card.order_id,
        is_active=card.is_active,
        redeemed_at=card.redeemed_at,
        redeemed_by_id=card.redeemed_by_id,
        redeemed_by_email=redeemed_by_email,
        state=state_of(card),
    )


async def default_expiry(
    session: AsyncSession, now: datetime | None = None
) -> datetime | None:
    """Expiry of a card issued now from the ``gift_card_validity_months`` setting
    (0 → never expires)."""
    months = int(await runtime_settings.get(SETTING_VALIDITY_MONTHS, session) or 0)
    if months <= 0:
        return None
    return (now or datetime.now(UTC)) + timedelta(days=30 * months)


async def issue(
    session: AsyncSession,
    *,
    kind: str,
    amount: Decimal,
    count: int = 1,
    recipient_email: str | None = None,
    note: str | None = None,
    expires_at: datetime | None = None,
    order_id: uuid.UUID | None = None,
    created_by_id: uuid.UUID | None = None,
) -> list[GiftCard]:
    """Create ``count`` cards; flushes, no commit. A voucher needs its
    recipient's e-mail."""
    currency = settings.REFERENCE_CURRENCY
    amount = quantize_amount(amount, currency)
    if amount <= 0:
        raise AppError(
            code="gift_card.amount.invalid",
            status_code=400,
            message="Le montant d'une carte cadeau doit être positif",
            details={},
        )
    email = (recipient_email or "").strip().lower() or None
    if kind == KIND_VOUCHER and email is None:
        raise AppError(
            code="gift_card.recipient.required",
            status_code=400,
            message="Un bon d'achat est nominatif : indiquez l'e-mail du client",
            details={},
        )
    cards = [
        GiftCard(
            code=generate_code(),
            kind=kind,
            amount=amount,
            currency=currency,
            recipient_email=email,
            note=(note or "").strip() or None,
            expires_at=expires_at,
            order_id=order_id,
            created_by_id=created_by_id,
        )
        for _ in range(count)
    ]
    session.add_all(cards)
    await session.flush()
    return cards


async def redeem(session: AsyncSession, *, code: str, user: User) -> GiftCard:
    """Turn the card into store credit of its holder; flushes, no commit.

    The code is looked up in its normalized form; a wrong code and a code of
    someone else's voucher both answer 404, so a guess learns nothing.
    """
    normalized = normalize_code(code)
    card = (
        await session.exec(select(GiftCard).where(col(GiftCard.code) == normalized))
    ).first()
    user_email = (user.email or "").strip().lower()
    if card is None or (
        card.kind == KIND_VOUCHER and (card.recipient_email or "").lower() != user_email
    ):
        raise AppError(
            code="gift_card.not_found",
            status_code=404,
            message="Ce code est inconnu",
            details={},
        )
    state = state_of(card)
    if state != "active":
        raise AppError(
            code=f"gift_card.{state}",
            status_code=409,
            message={
                "redeemed": "Ce code a déjà été utilisé",
                "expired": "Ce code a expiré",
                "cancelled": "Ce code a été annulé",
            }[state],
            details={"state": state},
        )
    label = "Bon d'achat" if card.kind == KIND_VOUCHER else "Carte cadeau"
    entry = await store_credit.grant(
        session,
        user_id=user.id,
        amount=card.amount,
        reason=f"{label} {mask_code(card.code)}",
        currency=card.currency,
        order_id=None,
        admin=None,
    )
    card.redeemed_at = datetime.now(UTC)
    card.redeemed_by_id = user.id
    card.store_credit_entry_id = entry.id
    session.add(card)
    await session.flush()
    return card


async def list_cards(
    session: AsyncSession,
    *,
    q: str | None = None,
    kind: str | None = None,
    state: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[GiftCardPublic], int]:
    """Admin listing, newest first. ``state`` filters on the computed state."""
    stmt = select(GiftCard)
    if kind:
        stmt = stmt.where(col(GiftCard.kind) == kind)
    if q:
        needle = f"%{q.strip()}%"
        stmt = stmt.where(
            col(GiftCard.code).ilike(needle)
            | col(GiftCard.recipient_email).ilike(needle)
            | col(GiftCard.note).ilike(needle)
        )
    now = datetime.now(UTC)
    if state == "redeemed":
        stmt = stmt.where(col(GiftCard.redeemed_at).is_not(None))
    elif state == "cancelled":
        stmt = stmt.where(
            col(GiftCard.redeemed_at).is_(None), col(GiftCard.is_active).is_(False)
        )
    elif state == "expired":
        stmt = stmt.where(
            col(GiftCard.redeemed_at).is_(None),
            col(GiftCard.is_active).is_(True),
            col(GiftCard.expires_at) <= now,
        )
    elif state == "active":
        stmt = stmt.where(
            col(GiftCard.redeemed_at).is_(None),
            col(GiftCard.is_active).is_(True),
            (col(GiftCard.expires_at).is_(None)) | (col(GiftCard.expires_at) > now),
        )
    count = (
        await session.exec(select(func.count()).select_from(stmt.subquery()))
    ).one()
    rows = (
        await session.exec(
            stmt.order_by(col(GiftCard.created_at).desc()).offset(skip).limit(limit)
        )
    ).all()
    redeemer_ids = {c.redeemed_by_id for c in rows if c.redeemed_by_id}
    emails: dict[uuid.UUID, str] = {}
    if redeemer_ids:
        for user_id, email in (
            await session.exec(
                select(User.id, User.email).where(col(User.id).in_(redeemer_ids))
            )
        ).all():
            emails[user_id] = email
    return [
        to_public(c, redeemed_by_email=emails.get(c.redeemed_by_id or uuid.UUID(int=0)))
        for c in rows
    ], int(count)


async def set_active(
    session: AsyncSession, *, card_id: uuid.UUID, active: bool
) -> GiftCard:
    """Cancel (or restore) an unredeemed card; flushes, no commit."""
    card = await session.get(GiftCard, card_id)
    if card is None:
        raise AppError(
            code="gift_card.not_found",
            status_code=404,
            message="Carte cadeau introuvable",
            details={"id": str(card_id)},
        )
    if card.redeemed_at is not None:
        raise AppError(
            code="gift_card.redeemed",
            status_code=409,
            message="Ce code a déjà été utilisé",
            details={"state": "redeemed"},
        )
    card.is_active = active
    session.add(card)
    await session.flush()
    return card


async def issue_for_order(
    session: AsyncSession, *, order_id: uuid.UUID
) -> list[GiftCard]:
    """The cards a paid order contains (lines of a ``gift_card_amount``
    product, one card per unit), issued once; flushes and publishes
    :data:`EVENT_GIFT_CARDS_ISSUED` when at least one card was created.

    Idempotent: an order that already has its cards gets none again, so the
    at-least-once outbox never doubles a customer's cards.
    """
    order = await session.get(Order, order_id)
    if order is None:
        return []
    lines = (
        await session.exec(select(OrderLine).where(col(OrderLine.order_id) == order_id))
    ).all()
    amounts: dict[uuid.UUID, Decimal] = {}
    if lines:
        for product in (
            await session.exec(
                select(Product).where(
                    col(Product.id).in_({line.product_id for line in lines}),
                    col(Product.gift_card_amount).is_not(None),
                )
            )
        ).all():
            if product.gift_card_amount is not None:
                amounts[product.id] = Decimal(product.gift_card_amount)
    rows = [
        (line, amounts[line.product_id]) for line in lines if line.product_id in amounts
    ]
    if not rows:
        return []
    existing = (
        await session.exec(
            select(func.count())
            .select_from(GiftCard)
            .where(col(GiftCard.order_id) == order_id)
        )
    ).one()
    if int(existing) > 0:
        return []
    buyer = await session.get(User, order.user_id)
    expires_at = await default_expiry(session)
    cards: list[GiftCard] = []
    for line, amount in rows:
        cards.extend(
            await issue(
                session,
                kind=KIND_GIFT_CARD,
                amount=Decimal(amount),
                count=int(line.quantity),
                recipient_email=buyer.email if buyer else None,
                note=f"Achetée — commande {order.order_number or order.id}",
                expires_at=expires_at,
                order_id=order_id,
            )
        )
    await outbox_registry.publish(
        session=session,
        event_type=EVENT_GIFT_CARDS_ISSUED,
        payload={
            "order_id": str(order_id),
            "user_id": str(order.user_id),
            "card_ids": [str(c.id) for c in cards],
            "currency": settings.REFERENCE_CURRENCY,
        },
        correlation_id=order_id,
    )
    logger.info("Order %s: %d gift card(s) issued", order_id, len(cards))
    return cards


async def cards_of_entry(
    session: AsyncSession, entry: StoreCreditEntry
) -> GiftCard | None:
    """The card a store-credit entry came from, if any (ledger display)."""
    return (
        await session.exec(
            select(GiftCard).where(col(GiftCard.store_credit_entry_id) == entry.id)
        )
    ).first()


def email_lines(cards: list[GiftCard]) -> list[dict[str, Any]]:
    """Template rows of the « vos cartes cadeaux » e-mail."""
    return [
        {
            "code": c.code,
            "amount": str(c.amount),
            "currency": c.currency,
            "expires_at": c.expires_at,
        }
        for c in cards
    ]
