"""Export comptable au format FEC.

L'invariant qui compte est l'équilibre : une écriture dont le débit ne fait pas
le crédit est rejetée à l'import par le logiciel comptable, et l'erreur ne se
découvre alors qu'au moment de la remise au comptable.
"""

import datetime
import uuid
from decimal import Decimal

from app.features.invoice.models.invoice import Invoice
from app.features.invoice.services.accounting_export import (
    FEC_COLUMNS,
    export_invoices_to_fec,
    invoice_to_fec_rows,
)


def _invoice() -> Invoice:
    """Facture à deux taux, dont un à 0 % (les frais non taxés)."""
    return Invoice(
        id=uuid.uuid4(),
        invoice_number="FAC-2026-00042",
        fiscal_year=2026,
        sequence_number=42,
        order_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        issued_at=datetime.datetime(2026, 8, 27, 10, 30, tzinfo=datetime.timezone.utc),
        currency="XPF",
        total_excl_tax=Decimal("1000.00"),
        total_tax=Decimal("130.00"),
        total_incl_tax=Decimal("1130.00"),
        snapshot={
            "buyer": {"name": "Jean Client", "email": "jean@example.test"},
            "order": {"number": "CMD-2026-000123"},
            "tax_breakdown": [
                {
                    "rate_pct": "0.00",
                    "base_excl_tax": "130.00",
                    "tax_amount": "0.00",
                    "total_incl_tax": "130.00",
                },
                {
                    "rate_pct": "16.00",
                    "base_excl_tax": "870.00",
                    "tax_amount": "130.00",
                    "total_incl_tax": "1000.00",
                },
            ],
        },
    )


def _total(rows: list[dict[str, str]], column: str) -> Decimal:
    return sum((Decimal(r[column].replace(",", ".")) for r in rows), Decimal("0"))


def test_fec_rows_balance_debit_against_credit() -> None:
    rows = invoice_to_fec_rows(_invoice())
    assert _total(rows, "Debit") == _total(rows, "Credit") == Decimal("1130.00")
    assert {r["CompteNum"] for r in rows} == {"411000", "707000", "445710"}


def test_a_zero_rate_group_produces_no_tax_line() -> None:
    """Un crédit de 0,00 au compte de TVA n'a pas de sens comptable."""
    rows = invoice_to_fec_rows(_invoice())
    tax_rows = [r for r in rows if r["CompteNum"] == "445710"]
    assert len(tax_rows) == 1
    assert tax_rows[0]["Credit"] == "130,00"
    # Les deux groupes produisent en revanche chacun leur ligne de vente.
    assert len([r for r in rows if r["CompteNum"] == "707000"]) == 2


def test_fec_file_uses_the_mandated_layout() -> None:
    content = export_invoices_to_fec([_invoice()])
    header, *lines = content.strip().split("\r\n")

    assert header.split("|") == FEC_COLUMNS
    assert len(lines) == 4  # débit client + 2 crédits ventes + 1 crédit taxe
    for line in lines:
        fields = line.split("|")
        assert fields[FEC_COLUMNS.index("EcritureDate")] == "20260827"
        assert fields[FEC_COLUMNS.index("PieceRef")] == "FAC-2026-00042"
        assert fields[FEC_COLUMNS.index("JournalCode")] == "VE"
        # Séparateur décimal virgule, comme l'exige la spécification.
        assert "," in fields[FEC_COLUMNS.index("Debit")]
        assert "," in fields[FEC_COLUMNS.index("Credit")]


def test_the_customer_line_carries_the_buyer_name() -> None:
    rows = invoice_to_fec_rows(_invoice())
    customer = next(r for r in rows if r["CompteNum"] == "411000")
    assert customer["CompAuxLib"] == "Jean Client"
    assert customer["Debit"] == "1130,00"


def test_an_invoice_without_snapshot_still_produces_a_balanced_entry() -> None:
    """Snapshot vide (facture ancienne ou tronquée) : pas d'exception, une
    écriture réduite au débit client — déséquilibrée mais explicite, plutôt
    qu'un export qui échoue en entier."""
    invoice = _invoice()
    invoice.snapshot = {}
    rows = invoice_to_fec_rows(invoice)
    assert len(rows) == 1
    assert rows[0]["CompteNum"] == "411000"


def test_fec_export_of_nothing_is_still_a_valid_file() -> None:
    assert export_invoices_to_fec([]).strip() == "|".join(FEC_COLUMNS)
