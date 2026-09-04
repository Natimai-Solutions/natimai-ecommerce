"""Integration tests: issuing the credit note that corrects an invoice (Z2).

Real DB — the numbering is a gap-free legal sequence held under a row lock,
and the idempotency key is a unique constraint. Neither can be exercised
against a mocked session.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.invoice.models.credit_note import CreditNote
from app.features.invoice.models.invoice import Invoice
from app.features.invoice.services.credit_note_service import (
    CreditNoteIssuanceError,
    get_credit_notes_for_order,
    issue_credit_note_for_refund,
)
from app.features.order.models.order import Order
from app.features.order.models.order_status import OrderStatus
from app.features.payment.models.payment import Payment
from app.features.payment.models.refund import Refund
from app.features.user.models.user import User

_BREAKDOWN = [
    {
        "rate_pct": "0",
        "base_excl_tax": "10000.00",
        "tax_amount": "0.00",
        "total_incl_tax": "10000.00",
    },
    {
        "rate_pct": "16",
        "base_excl_tax": "77586.21",
        "tax_amount": "12413.79",
        "total_incl_tax": "90000.00",
    },
]


async def _seed(
    session: AsyncSession, *, invoice_total: str = "100000.00"
) -> tuple[uuid.UUID, uuid.UUID]:
    """An invoiced, paid order. Returns (order_id, payment_id)."""
    user = User(
        email=f"c+{uuid.uuid4().hex[:8]}@test.local",
        is_active=True,
        hashed_password="x",
    )
    status = OrderStatus(name=f"Paid-{uuid.uuid4().hex[:6]}")
    session.add_all([user, status])
    await session.flush()

    order = Order(
        user_id=user.id,
        order_status_id=status.id,
        total_amount=Decimal(invoice_total),
        currency="XPF",
    )
    session.add(order)
    await session.flush()

    payment = Payment(
        amount=Decimal(invoice_total),
        currency="XPF",
        order_id=order.id,
        user_id=user.id,
    )
    session.add(payment)
    await session.flush()

    session.add(
        Invoice(
            invoice_number=f"FAC-2026-{uuid.uuid4().int % 100000:05d}",
            fiscal_year=2026,
            sequence_number=1,
            order_id=order.id,
            user_id=user.id,
            issued_at=datetime(2026, 3, 4, tzinfo=timezone.utc),
            currency="XPF",
            total_excl_tax=Decimal("87586.21"),
            total_tax=Decimal("12413.79"),
            total_incl_tax=Decimal(invoice_total),
            snapshot={
                "seller": {"name": "Natimai"},
                "buyer": {"name": "Client", "email": user.email},
                "order": {"number": "CMD-2026-00042"},
                "tax_breakdown": _BREAKDOWN,
            },
        )
    )
    await session.flush()
    return order.id, payment.id


async def _refund(
    session: AsyncSession,
    *,
    order_id: uuid.UUID,
    payment_id: uuid.UUID,
    amount: str,
    reason: str | None = None,
) -> uuid.UUID:
    refund = Refund(
        payment_id=payment_id,
        order_id=order_id,
        amount=Decimal(amount),
        currency="XPF",
        reason=reason,
        status="completed",
    )
    session.add(refund)
    await session.flush()
    return refund.id


@pytest.mark.asyncio
async def test_a_full_refund_produces_a_credit_note(db_session: AsyncSession) -> None:
    order_id, payment_id = await _seed(db_session)
    refund_id = await _refund(
        db_session,
        order_id=order_id,
        payment_id=payment_id,
        amount="100000.00",
        reason="Commande annulée",
    )
    await db_session.commit()

    note = await issue_credit_note_for_refund(db_session, refund_id=refund_id)

    assert note.credit_note_number.startswith("AV-")
    assert note.total_incl_tax == Decimal("100000.00")
    assert note.total_excl_tax + note.total_tax == Decimal("100000.00")
    assert note.reason == "Commande annulée"


@pytest.mark.asyncio
async def test_issuance_is_idempotent_per_refund(db_session: AsyncSession) -> None:
    """The outbox delivers at least once; a second number must not be burned."""
    order_id, payment_id = await _seed(db_session)
    refund_id = await _refund(
        db_session, order_id=order_id, payment_id=payment_id, amount="100000.00"
    )
    await db_session.commit()

    first = await issue_credit_note_for_refund(db_session, refund_id=refund_id)
    second = await issue_credit_note_for_refund(db_session, refund_id=refund_id)

    assert first.id == second.id
    assert first.credit_note_number == second.credit_note_number


@pytest.mark.asyncio
async def test_numbering_is_sequential_and_gap_free(db_session: AsyncSession) -> None:
    numbers: list[str] = []
    for _ in range(3):
        order_id, payment_id = await _seed(db_session)
        refund_id = await _refund(
            db_session, order_id=order_id, payment_id=payment_id, amount="1000.00"
        )
        await db_session.commit()
        note = await issue_credit_note_for_refund(db_session, refund_id=refund_id)
        numbers.append(note.credit_note_number)

    year = datetime.now(timezone.utc).year
    assert numbers == [
        f"AV-{year}-00001",
        f"AV-{year}-00002",
        f"AV-{year}-00003",
    ]


@pytest.mark.asyncio
async def test_successive_partial_refunds_each_get_a_note(
    db_session: AsyncSession,
) -> None:
    order_id, payment_id = await _seed(db_session)
    first_refund = await _refund(
        db_session, order_id=order_id, payment_id=payment_id, amount="30000.00"
    )
    second_refund = await _refund(
        db_session, order_id=order_id, payment_id=payment_id, amount="20000.00"
    )
    await db_session.commit()

    await issue_credit_note_for_refund(db_session, refund_id=first_refund)
    await issue_credit_note_for_refund(db_session, refund_id=second_refund)

    notes = await get_credit_notes_for_order(db_session, order_id=order_id)
    assert len(notes) == 2
    assert sum((note.total_incl_tax for note in notes), Decimal("0")) == Decimal(
        "50000.00"
    )


@pytest.mark.asyncio
async def test_crediting_more_than_the_invoice_is_refused(
    db_session: AsyncSession,
) -> None:
    """Two partial refunds must never add up past the invoice total."""
    order_id, payment_id = await _seed(db_session)
    first_refund = await _refund(
        db_session, order_id=order_id, payment_id=payment_id, amount="90000.00"
    )
    second_refund = await _refund(
        db_session, order_id=order_id, payment_id=payment_id, amount="20000.00"
    )
    await db_session.commit()

    await issue_credit_note_for_refund(db_session, refund_id=first_refund)

    with pytest.raises(CreditNoteIssuanceError, match="exceed"):
        await issue_credit_note_for_refund(db_session, refund_id=second_refund)


@pytest.mark.asyncio
async def test_an_uninvoiced_order_cannot_be_credited(
    db_session: AsyncSession,
) -> None:
    """Refunding before invoicing leaves nothing to correct."""
    user = User(
        email=f"c+{uuid.uuid4().hex[:8]}@test.local",
        is_active=True,
        hashed_password="x",
    )
    status = OrderStatus(name=f"Pending-{uuid.uuid4().hex[:6]}")
    db_session.add_all([user, status])
    await db_session.flush()
    order = Order(
        user_id=user.id,
        order_status_id=status.id,
        total_amount=Decimal("1000.00"),
        currency="XPF",
    )
    db_session.add(order)
    await db_session.flush()
    payment = Payment(
        amount=Decimal("1000.00"), currency="XPF", order_id=order.id, user_id=user.id
    )
    db_session.add(payment)
    await db_session.flush()
    refund_id = await _refund(
        db_session, order_id=order.id, payment_id=payment.id, amount="1000.00"
    )
    await db_session.commit()

    with pytest.raises(CreditNoteIssuanceError, match="no invoice"):
        await issue_credit_note_for_refund(db_session, refund_id=refund_id)


@pytest.mark.asyncio
async def test_an_unknown_refund_is_refused(db_session: AsyncSession) -> None:
    with pytest.raises(CreditNoteIssuanceError, match="not found"):
        await issue_credit_note_for_refund(db_session, refund_id=uuid.uuid4())


@pytest.mark.asyncio
async def test_the_note_points_back_at_the_invoice(db_session: AsyncSession) -> None:
    order_id, payment_id = await _seed(db_session)
    refund_id = await _refund(
        db_session, order_id=order_id, payment_id=payment_id, amount="100000.00"
    )
    await db_session.commit()

    note = await issue_credit_note_for_refund(db_session, refund_id=refund_id)

    invoice = await db_session.get(Invoice, note.invoice_id)
    assert invoice is not None
    assert invoice.order_id == order_id
    assert note.snapshot["invoice"]["number"] == invoice.invoice_number

    stored = await db_session.get(CreditNote, note.id)
    assert stored is not None
    assert stored.refund_id == refund_id
