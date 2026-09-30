"""Store credit (« avoir-crédit ») : balance, grants and use at checkout.

Using credit on an order creates a settled ``Payment`` of provider
``store_credit`` for the part it covers (the deposit, or the total), next to
the money payment for the rest. The payment guards and handlers therefore
see one part settled by several payments, and only act on the order once
the part is fully covered (:func:`part_coverage`).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.errors import AppError
from app.features.payment.crud.payment import crud_payment
from app.features.payment.crud.payment_status import crud_payment_status
from app.features.payment.models.payment import Payment
from app.features.payment.models.store_credit import StoreCreditEntry
from app.features.payment.services.deposit import expected_amount
from app.outbox.registry import outbox_registry
from app.utils.money import quantize_amount

STORE_CREDIT_PROVIDER = "store_credit"
PAYMENT_STATUS_COMPLETED = "Completed"
EVENT_PAYMENT_CAPTURED = "payment.captured"

#: Payment statuses that count as money in.
SETTLED_PAYMENT_STATUSES: frozenset[str] = frozenset(
    {"Completed", "Authorized", "Refunded", "PartiallyRefunded"}
)
#: Payment statuses of a payment that will never settle.
DEAD_PAYMENT_STATUSES: frozenset[str] = frozenset({"Failed", "Cancelled"})


async def balance(session: AsyncSession, user_id: uuid.UUID) -> Decimal:
    """Σ of the customer's ledger."""
    total = (
        await session.exec(
            select(func.coalesce(func.sum(col(StoreCreditEntry.amount)), 0)).where(
                col(StoreCreditEntry.user_id) == user_id,
                col(StoreCreditEntry.is_active).is_(True),
            )
        )
    ).one()
    return Decimal(total)


async def entries(session: AsyncSession, user_id: uuid.UUID) -> list[StoreCreditEntry]:
    return list(
        (
            await session.exec(
                select(StoreCreditEntry)
                .where(
                    col(StoreCreditEntry.user_id) == user_id,
                    col(StoreCreditEntry.is_active).is_(True),
                )
                .order_by(col(StoreCreditEntry.created_at).desc())
            )
        ).all()
    )


async def grant(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    amount: Decimal,
    reason: str,
    currency: str,
    order_id: uuid.UUID | None,
    admin: Any,
) -> StoreCreditEntry:
    """Grant (positive) or revoke (negative) credit; a revocation cannot take
    the balance below zero. Flushes, no commit."""
    amount = quantize_amount(amount, currency)
    if amount == 0:
        raise AppError(
            code="store_credit.amount.invalid",
            status_code=400,
            message="Le montant de l'avoir doit être différent de zéro",
            details={},
        )
    if amount < 0 and await balance(session, user_id) + amount < 0:
        raise AppError(
            code="store_credit.insufficient",
            status_code=409,
            message="Le solde d'avoir ne peut pas devenir négatif",
            details={"user_id": str(user_id)},
        )
    entry = StoreCreditEntry(
        user_id=user_id,
        amount=amount,
        currency=currency,
        kind="grant" if amount > 0 else "revoke",
        reason=reason.strip(),
        order_id=order_id,
        created_by_id=getattr(admin, "id", None),
    )
    session.add(entry)
    await session.flush()
    return entry


async def apply_to_order(
    session: AsyncSession,
    *,
    order: Any,
    user: Any,
    amount: Decimal,
    kind: str,
) -> Payment:
    """Spend ``amount`` of the customer's credit on ``order``: a « use » entry
    and a settled ``store_credit`` payment of ``kind``, whose capture event
    drives the order like any other payment. Flushes, no commit."""
    currency = order.currency or "XPF"
    amount = quantize_amount(amount, currency)
    available = await balance(session, user.id)
    if amount <= 0 or amount > available:
        raise AppError(
            code="store_credit.insufficient",
            status_code=409,
            message="Avoir insuffisant pour ce montant",
            details={"available": str(available), "requested": str(amount)},
        )
    payment = Payment(
        order_id=order.id,
        user_id=user.id,
        amount=amount,
        currency=currency,
        provider_code=STORE_CREDIT_PROVIDER,
        provider_reference=f"avoir:{order.order_number or order.id}",
        kind=kind,
    )
    completed = await crud_payment_status.get_by_name(
        session, name=PAYMENT_STATUS_COMPLETED
    )
    if completed is not None:
        payment.payment_status_id = completed.id
    session.add(payment)
    await session.flush()
    session.add(
        StoreCreditEntry(
            user_id=user.id,
            amount=-amount,
            currency=currency,
            kind="use",
            reason=f"Commande {order.order_number or order.id}",
            order_id=order.id,
            payment_id=payment.id,
        )
    )
    await outbox_registry.publish(
        session=session,
        event_type=EVENT_PAYMENT_CAPTURED,
        payload={
            "payment_id": str(payment.id),
            "order_id": str(order.id),
            "user_id": str(user.id),
            "provider_code": STORE_CREDIT_PROVIDER,
            "total_amount": str(amount),
            "currency": currency,
            "action": "store_credit",
            "admin_user_id": None,
            "reason": None,
            "reference": payment.provider_reference,
            "metadata": {"kind": kind},
        },
        correlation_id=payment.id,
    )
    await session.flush()
    return payment


def settled_by_kind(
    order_payments: Sequence[tuple[Any, str | None]],
) -> tuple[dict[str, Decimal], set[str]]:
    """``({kind: Σ settled amounts}, {kinds with a payment still pending})``
    from ``crud_payment.list_with_status_by_order_id``."""
    settled: dict[str, Decimal] = {}
    pending: set[str] = set()
    for payment, status_name in order_payments:
        kind = getattr(payment, "kind", None) or "full"
        if status_name in SETTLED_PAYMENT_STATUSES:
            settled[kind] = settled.get(kind, Decimal(0)) + Decimal(payment.amount)
        elif status_name not in DEAD_PAYMENT_STATUSES:
            pending.add(kind)
    return settled, pending


async def part_coverage(
    session: AsyncSession, *, payment: Any, order: Any
) -> tuple[Decimal, Decimal, bool]:
    """How far the part of the order this payment belongs to is settled:
    ``(covered, expected, still_pending)`` — covered counts this payment
    even if its status is not written yet."""
    kind = getattr(payment, "kind", None) or "full"
    rows = await crud_payment.list_with_status_by_order_id(session, order_id=order.id)
    others = [(p, s) for p, s in rows if p.id != payment.id]
    settled, pending = settled_by_kind(others)
    covered = settled.get(kind, Decimal(0)) + Decimal(payment.amount)
    return covered, expected_amount(order, kind), kind in pending


__all__ = [
    "DEAD_PAYMENT_STATUSES",
    "SETTLED_PAYMENT_STATUSES",
    "STORE_CREDIT_PROVIDER",
    "apply_to_order",
    "balance",
    "entries",
    "grant",
    "part_coverage",
    "settled_by_kind",
]
