"""Prices in whole currency units, one tax-split rule (audit 2026-11).

Sale prices were rounded to the cent whatever the currency: 11 600,37 F
was shown 11 600 F and two of them billed 23 201 F. The invoice, the credit
note and the margin each split « TTC → HT + TVA » their own way.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.config import settings
from app.features.invoice.services.credit_note_service import _prorated_breakdown
from app.features.invoice.services.invoice_service import _split_incl_tax
from app.features.product.services.margin import compute_margin
from app.features.product.services.pricing_parameters import apply_payment_commission
from app.utils.money import reference_price, split_incl_tax


@pytest.mark.parametrize(
    ("currency", "raw", "expected"),
    [
        ("XPF", "11600.37", "11600"),
        ("XPF", "11600.50", "11601"),
        ("EUR", "97.205", "97.21"),
    ],
)
def test_a_price_is_rounded_to_the_unit_of_the_reference_currency(
    monkeypatch: pytest.MonkeyPatch, currency: str, raw: str, expected: str
) -> None:
    monkeypatch.setattr(settings, "REFERENCE_CURRENCY", currency)
    assert reference_price(Decimal(raw)) == Decimal(expected)
    # The last step of every computed sale price.
    assert apply_payment_commission(Decimal(raw), Decimal("0")) == Decimal(expected)


def test_what_is_shown_is_what_is_billed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "REFERENCE_CURRENCY", "XPF")
    unit = apply_payment_commission(Decimal("11600.37"), Decimal("0"))
    assert unit * 2 == Decimal("23200")  # two lines of 11 600 F, not 23 201


def test_one_tax_split_for_invoice_credit_note_and_margin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "REFERENCE_CURRENCY", "XPF")
    excl, tax = split_incl_tax(Decimal("23200"), Decimal("16"), "XPF")
    assert (excl, tax) == (Decimal("20000"), Decimal("3200"))
    assert excl + tax == Decimal("23200")
    assert _split_incl_tax(Decimal("23200"), Decimal("16"), "XPF") == (excl, tax)

    # A full credit note mirrors the invoice's breakdown exactly.
    invoice_rows = [
        {
            "rate_pct": "16",
            "base_excl_tax": "20000",
            "tax_amount": "3200",
            "total_incl_tax": "23200",
        },
        {
            "rate_pct": "5",
            "base_excl_tax": "952",
            "tax_amount": "48",
            "total_incl_tax": "1000",
        },
    ]
    rows, total_excl, total_tax = _prorated_breakdown(
        invoice_breakdown=invoice_rows,
        invoice_total_incl=Decimal("24200"),
        credited_incl=Decimal("24200"),
        currency="XPF",
    )
    assert [(r["base_excl_tax"], r["tax_amount"]) for r in rows] == [
        ("20000", "3200"),
        ("952", "48"),
    ]
    assert total_excl + total_tax == Decimal("24200")

    # The margin reads the same price excl. tax, in whole francs.
    figures = compute_margin(
        price_incl_tax=Decimal("23200"),
        tax_rate_pct=Decimal("16"),
        unit_cost=Decimal("15000.4"),
    )
    assert figures is not None
    assert figures.price_excl_tax == excl
    assert figures.unit_cost == Decimal("15000")
    assert figures.margin_amount == Decimal("5000")
