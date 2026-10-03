"""Tax arithmetic of a credit note (Z2).

The split is taken from the original invoice, never recomputed from the
catalogue: crediting at today's rate a sale taxed at last year's would not tie
out. What matters is that the three totals reconcile exactly to the amount
actually refunded — an accountant checks that first.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import cast

import pytest

from app.features.invoice.models.invoice import Invoice
from app.features.invoice.services.credit_note_service import (
    CreditNoteIssuanceError,
    _prorated_breakdown,
    build_credit_note_snapshot,
)
from app.features.invoice.services.numbering import (
    format_credit_note_number,
    format_invoice_number,
)
from app.features.payment.models.refund import Refund

_TWO_RATES = [
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


def _totals(rows: list[dict[str, str]]) -> tuple[Decimal, Decimal, Decimal]:
    excl = sum((Decimal(row["base_excl_tax"]) for row in rows), Decimal("0"))
    tax = sum((Decimal(row["tax_amount"]) for row in rows), Decimal("0"))
    incl = sum((Decimal(row["total_incl_tax"]) for row in rows), Decimal("0"))
    return excl, tax, incl


def test_a_full_refund_credits_the_whole_invoice() -> None:
    rows, excl, tax = _prorated_breakdown(
        invoice_breakdown=_TWO_RATES,
        invoice_total_incl=Decimal("100000.00"),
        credited_incl=Decimal("100000.00"),
        currency="XPF",
    )

    _, _, incl = _totals(rows)
    assert incl == Decimal("100000.00")
    assert excl + tax == Decimal("100000.00")


def test_a_partial_refund_is_split_pro_rata() -> None:
    """Half the invoice credits half of each tax group."""
    rows, excl, tax = _prorated_breakdown(
        invoice_breakdown=_TWO_RATES,
        invoice_total_incl=Decimal("100000.00"),
        credited_incl=Decimal("50000.00"),
        currency="XPF",
    )

    by_rate = {row["rate_pct"]: Decimal(row["total_incl_tax"]) for row in rows}
    assert by_rate["0"] == Decimal("5000")
    assert by_rate["16"] == Decimal("45000")
    assert excl + tax == Decimal("50000.00")


def test_the_totals_always_reconcile_to_the_refunded_amount() -> None:
    """Rounding must never leave the document a franc short."""
    for credited in ("1", "7", "333", "12345", "99999"):
        rows, excl, tax = _prorated_breakdown(
            invoice_breakdown=_TWO_RATES,
            invoice_total_incl=Decimal("100000.00"),
            credited_incl=Decimal(credited),
            currency="XPF",
        )
        _, _, incl = _totals(rows)
        assert incl == Decimal(credited), credited
        assert excl + tax == Decimal(credited), credited


def test_the_remainder_lands_on_the_last_group() -> None:
    """Somebody has to carry the rounding; it is stated, not accidental."""
    rows, _, _ = _prorated_breakdown(
        invoice_breakdown=_TWO_RATES,
        invoice_total_incl=Decimal("100000.00"),
        credited_incl=Decimal("333"),
        currency="XPF",
    )
    total = sum((Decimal(row["total_incl_tax"]) for row in rows), Decimal("0"))
    assert total == Decimal("333")


def test_a_single_rate_invoice_credits_that_rate() -> None:
    rows, excl, tax = _prorated_breakdown(
        invoice_breakdown=[
            {
                "rate_pct": "16",
                "base_excl_tax": "86206.90",
                "tax_amount": "13793.10",
                "total_incl_tax": "100000.00",
            }
        ],
        invoice_total_incl=Decimal("100000.00"),
        credited_incl=Decimal("25000"),
        currency="XPF",
    )

    assert len(rows) == 1
    assert rows[0]["rate_pct"] == "16"
    assert excl + tax == Decimal("25000")


def test_empty_groups_are_ignored() -> None:
    rows, _, _ = _prorated_breakdown(
        invoice_breakdown=[
            {
                "rate_pct": "0",
                "base_excl_tax": "0.00",
                "tax_amount": "0.00",
                "total_incl_tax": "0.00",
            },
            *_TWO_RATES,
        ],
        invoice_total_incl=Decimal("100000.00"),
        credited_incl=Decimal("100000.00"),
        currency="XPF",
    )

    assert len(rows) == 2


def test_an_invoice_without_a_breakdown_cannot_be_credited() -> None:
    """Better no document than one whose taxes are invented."""
    with pytest.raises(CreditNoteIssuanceError):
        _prorated_breakdown(
            invoice_breakdown=[],
            invoice_total_incl=Decimal("100000.00"),
            credited_incl=Decimal("100.00"),
            currency="XPF",
        )


# -- numbering --------------------------------------------------------------


def test_credit_notes_and_invoices_use_distinct_prefixes() -> None:
    """The two sequences are legally distinct and must never be confused."""
    assert format_credit_note_number(42, fiscal_year=2026) == "AV-2026-00042"
    assert format_invoice_number(42, fiscal_year=2026) == "FAC-2026-00042"


# -- snapshot ---------------------------------------------------------------


def _invoice(total: str = "100000.00") -> SimpleNamespace:
    return SimpleNamespace(
        id="11111111-1111-1111-1111-111111111111",
        invoice_number="FAC-2026-00007",
        issued_at=datetime(2026, 3, 4, tzinfo=UTC),
        currency="XPF",
        total_incl_tax=Decimal(total),
        snapshot={
            "seller": {"name": "Natimai"},
            "buyer": {"name": "Client", "email": "c@test.pf"},
            "order": {"number": "CMD-2026-00042"},
            "tax_breakdown": _TWO_RATES,
        },
    )


def test_the_snapshot_reuses_the_invoice_identities() -> None:
    """Re-rendering must reproduce the parties as they were at the sale."""
    snapshot = build_credit_note_snapshot(
        invoice=cast(Invoice, _invoice()),
        refund=cast(
            Refund, SimpleNamespace(amount=Decimal("100000.00"), reason="Annulation")
        ),
        breakdown=_TWO_RATES,
    )

    assert snapshot["seller"]["name"] == "Natimai"
    assert snapshot["buyer"]["email"] == "c@test.pf"
    assert snapshot["invoice"]["number"] == "FAC-2026-00007"
    assert snapshot["reason"] == "Annulation"


def test_the_snapshot_flags_a_full_refund() -> None:
    full = build_credit_note_snapshot(
        invoice=cast(Invoice, _invoice()),
        refund=cast(Refund, SimpleNamespace(amount=Decimal("100000.00"), reason=None)),
        breakdown=_TWO_RATES,
    )
    partial = build_credit_note_snapshot(
        invoice=cast(Invoice, _invoice()),
        refund=cast(Refund, SimpleNamespace(amount=Decimal("40000.00"), reason=None)),
        breakdown=_TWO_RATES,
    )

    assert full["is_full_refund"] is True
    assert partial["is_full_refund"] is False
