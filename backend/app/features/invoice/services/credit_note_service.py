"""Issue the credit note that corrects an invoice after a refund (Z2).

A refund changed a payment status and nothing else: the money went back while
the invoice stayed in the books claiming a sale that no longer held. An issued
invoice is immutable and its sequence gap-free, so the correction cannot be an
edit — it is a second document pointing at the first.

The tax split is taken **from the original invoice**, not recomputed from the
catalogue: crediting at today's rate a sale taxed at last year's would not tie
out. On a partial refund the invoice's breakdown is applied pro rata, and the
last rate group absorbs the rounding remainder so that
``excl + tax == refunded amount`` holds exactly, as it does on the invoice.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.invoice.models.credit_note import CreditNote, CreditNotePublic
from app.features.invoice.models.invoice import Invoice
from app.features.invoice.services.integrity import seal_document
from app.features.invoice.services.numbering import allocate_credit_note_number
from app.features.payment.models.refund import Refund
from app.utils.money import quantize_amount, split_incl_tax

logger = logging.getLogger(__name__)

_ZERO = Decimal("0")


def credit_note_to_public(credit_note: CreditNote) -> CreditNotePublic:
    """API view of a credit note; references come from the frozen snapshot."""
    snapshot: dict[str, Any] = getattr(credit_note, "snapshot", None) or {}
    order_snapshot = snapshot.get("order") or {}
    invoice_snapshot = snapshot.get("invoice") or {}
    return CreditNotePublic(
        id=credit_note.id,
        credit_note_number=credit_note.credit_note_number,
        fiscal_year=credit_note.fiscal_year,
        invoice_id=credit_note.invoice_id,
        order_id=credit_note.order_id,
        issued_at=credit_note.issued_at,
        currency=credit_note.currency,
        total_excl_tax=credit_note.total_excl_tax,
        total_tax=credit_note.total_tax,
        total_incl_tax=credit_note.total_incl_tax,
        reason=credit_note.reason,
        order_number=order_snapshot.get("number") or None,
        invoice_number=invoice_snapshot.get("number") or None,
    )


class InvoiceNotIssuedError(RuntimeError):
    """The order has no invoice *yet*: it is issued asynchronously after the
    capture, and a quick refund can overtake it (audit 2026-11)."""


class CreditNoteIssuanceError(RuntimeError):
    """Raised when a credit note cannot be issued for a refund."""


async def get_credit_note_for_refund(
    session: AsyncSession, *, refund_id: uuid.UUID
) -> CreditNote | None:
    """Return the credit note already issued for ``refund_id``, if any."""
    result = await session.exec(
        select(CreditNote).where(CreditNote.refund_id == refund_id)
    )
    return result.first()


async def get_credit_notes_for_order(
    session: AsyncSession, *, order_id: uuid.UUID
) -> list[CreditNote]:
    """Every credit note issued against ``order_id``, oldest first."""
    result = await session.exec(
        select(CreditNote)
        .where(CreditNote.order_id == order_id)
        .order_by(CreditNote.issued_at)  # type: ignore[arg-type]
    )
    return list(result.all())


def _prorated_breakdown(
    *,
    invoice_breakdown: list[dict[str, str]],
    invoice_total_incl: Decimal,
    credited_incl: Decimal,
    currency: str,
) -> tuple[list[dict[str, str]], Decimal, Decimal]:
    """Split ``credited_incl`` across the invoice's tax groups, pro rata.

    Returns ``(breakdown, total_excl, total_tax)``. The remainder left by
    rounding each group is carried on the last one, so the three totals always
    reconcile to the amount actually refunded.
    """
    usable = [
        row for row in invoice_breakdown if Decimal(row["total_incl_tax"]) != _ZERO
    ]
    if not usable or invoice_total_incl == _ZERO:
        raise CreditNoteIssuanceError(
            "Original invoice carries no tax breakdown to credit against"
        )

    rows: list[dict[str, str]] = []
    allocated_incl = _ZERO
    for index, row in enumerate(usable):
        is_last = index == len(usable) - 1
        if is_last:
            incl = credited_incl - allocated_incl
        else:
            share = Decimal(row["total_incl_tax"]) / invoice_total_incl
            incl = quantize_amount(credited_incl * share, currency)
        allocated_incl += incl

        excl, tax = split_incl_tax(incl, Decimal(row["rate_pct"]), currency)
        rows.append(
            {
                "rate_pct": row["rate_pct"],
                "base_excl_tax": str(excl),
                "tax_amount": str(tax),
                "total_incl_tax": str(incl),
            }
        )

    total_excl = sum((Decimal(row["base_excl_tax"]) for row in rows), _ZERO)
    total_tax = sum((Decimal(row["tax_amount"]) for row in rows), _ZERO)
    return rows, total_excl, total_tax


def build_credit_note_snapshot(
    *, invoice: Invoice, refund: Refund, breakdown: list[dict[str, str]]
) -> dict[str, Any]:
    """Freeze what the credit note prints, reusing the invoice's identities."""
    invoice_snapshot = dict(invoice.snapshot)
    return {
        "seller": invoice_snapshot.get("seller", {}),
        "buyer": invoice_snapshot.get("buyer", {}),
        "order": invoice_snapshot.get("order", {}),
        "invoice": {
            "id": str(invoice.id),
            "number": invoice.invoice_number,
            "issued_at": invoice.issued_at.isoformat(),
            "total_incl_tax": str(invoice.total_incl_tax),
        },
        "currency": invoice.currency,
        "reason": refund.reason or "",
        "tax_breakdown": breakdown,
        "is_full_refund": quantize_amount(refund.amount, invoice.currency)
        == quantize_amount(invoice.total_incl_tax, invoice.currency),
    }


async def issue_credit_note_for_refund(
    session: AsyncSession,
    *,
    refund_id: uuid.UUID,
    issued_at: datetime | None = None,
    commit: bool = True,
) -> CreditNote:
    """Issue the credit note for a completed refund (idempotent).

    Returns the existing document when the refund already has one, so a
    replayed ``payment.refunded`` never produces a second one.
    """
    existing = await get_credit_note_for_refund(session, refund_id=refund_id)
    if existing is not None:
        logger.info(
            "Credit note %s already issued for refund %s — reusing",
            existing.credit_note_number,
            refund_id,
        )
        return existing

    refund = await session.get(Refund, refund_id)
    if refund is None:
        raise CreditNoteIssuanceError(f"Refund {refund_id} not found")
    if refund.order_id is None:
        raise CreditNoteIssuanceError(
            f"Refund {refund_id} is not linked to an order — nothing to credit"
        )

    result = await session.exec(
        select(Invoice).where(Invoice.order_id == refund.order_id)
    )
    invoice = result.first()
    if invoice is None:
        raise InvoiceNotIssuedError(f"Order {refund.order_id} has no invoice yet")

    currency = invoice.currency
    credited_incl = quantize_amount(refund.amount, currency)
    if credited_incl <= _ZERO:
        raise CreditNoteIssuanceError(f"Refund {refund_id} has a non-positive amount")

    already_credited = sum(
        (
            note.total_incl_tax
            for note in await get_credit_notes_for_order(
                session, order_id=refund.order_id
            )
        ),
        _ZERO,
    )
    if already_credited + credited_incl > invoice.total_incl_tax:
        raise CreditNoteIssuanceError(
            f"Crediting {credited_incl} on top of {already_credited} would exceed "
            f"invoice {invoice.invoice_number} total {invoice.total_incl_tax}"
        )

    breakdown, total_excl, total_tax = _prorated_breakdown(
        invoice_breakdown=list(invoice.snapshot.get("tax_breakdown", [])),
        invoice_total_incl=invoice.total_incl_tax,
        credited_incl=credited_incl,
        currency=currency,
    )

    issuance_date = issued_at or datetime.now(UTC)
    number, sequence_number = await allocate_credit_note_number(
        session, fiscal_year=issuance_date.year
    )

    credit_note = CreditNote(
        credit_note_number=number,
        fiscal_year=issuance_date.year,
        sequence_number=sequence_number,
        invoice_id=invoice.id,
        refund_id=refund.id,
        order_id=refund.order_id,
        user_id=invoice.user_id,
        issued_at=issuance_date,
        currency=currency,
        total_excl_tax=total_excl,
        total_tax=total_tax,
        total_incl_tax=credited_incl,
        reason=refund.reason,
        snapshot=build_credit_note_snapshot(
            invoice=invoice, refund=refund, breakdown=breakdown
        ),
    )
    # Under the year's counter lock taken by the allocation above.
    await seal_document(session, credit_note)
    session.add(credit_note)

    # Read what the log needs BEFORE the commit: a commit expires every loaded
    # instance, and touching `invoice` afterwards would trigger a synchronous
    # lazy-load (MissingGreenlet) in the async session.
    invoice_number = invoice.invoice_number

    if commit:
        await session.commit()
        await session.refresh(credit_note)

    logger.info(
        "Credit note %s issued for refund %s against invoice %s (%s %s)",
        number,
        refund_id,
        invoice_number,
        credited_incl,
        currency,
    )
    return credit_note
