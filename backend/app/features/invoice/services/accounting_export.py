"""Export comptable des factures émises — format FEC (M3).

Produit les 18 colonnes du *Fichier des Écritures Comptables* dans leur ordre
imposé, séparées par des barres verticales : c'est la forme que tout logiciel
comptable français (Sage compris) sait importer. Une facture devient une
écriture équilibrée :

* une ligne au débit du compte client (total TTC),
* une ligne au crédit du compte de ventes par taux (base HT),
* une ligne au crédit du compte de taxe par taux (montant de taxe).

À distinguer de l'export CSV de `admin_invoices` : celui-ci liste les factures
à plat pour vérifier d'un coup d'œil la continuité de la numérotation, il n'est
pas importable comme un journal.

Les numéros de compte viennent du plan comptable général et restent des
constantes de module : le comptable peut les mapper autrement, et un seul
endroit à changer vaut mieux que des littéraux disséminés.

Les montants utilisent la virgule décimale et les dates la forme ``AAAAMMJJ``,
toutes deux exigées par la spécification.
"""

from __future__ import annotations

import csv
import datetime
import io
from decimal import Decimal
from typing import Any

from app.features.invoice.models.invoice import Invoice

FEC_COLUMNS = [
    "JournalCode",
    "JournalLib",
    "EcritureNum",
    "EcritureDate",
    "CompteNum",
    "CompteLib",
    "CompAuxNum",
    "CompAuxLib",
    "PieceRef",
    "PieceDate",
    "EcritureLib",
    "Debit",
    "Credit",
    "EcritureLet",
    "DateLet",
    "ValidDate",
    "Montantdevise",
    "Idevise",
]

JOURNAL_CODE = "VE"
JOURNAL_LABEL = "Ventes"
ACCOUNT_CUSTOMER = "411000"
ACCOUNT_CUSTOMER_LABEL = "Clients"
ACCOUNT_SALES = "707000"
ACCOUNT_SALES_LABEL = "Ventes de marchandises"
ACCOUNT_TAX = "445710"
ACCOUNT_TAX_LABEL = "Taxe collectee"


def _amount(value: Decimal | str | int) -> str:
    """Montants FEC : deux décimales, séparateur virgule."""
    return f"{Decimal(str(value)):.2f}".replace(".", ",")


def _date(value: datetime.datetime) -> str:
    """Dates FEC : AAAAMMJJ."""
    return value.strftime("%Y%m%d")


def invoice_to_fec_rows(invoice: Invoice) -> list[dict[str, str]]:
    """Déplie une facture en son jeu d'écritures équilibrées."""
    entry_date = _date(invoice.issued_at)
    label = f"Facture {invoice.invoice_number}"

    # Le modèle de main range tout dans `snapshot` (figé à l'émission) plutôt
    # que dans des colonnes dédiées : c'est cette copie qui fait foi, elle ne
    # bouge plus même si le client change de nom ensuite.
    snapshot: dict[str, Any] = invoice.snapshot or {}
    buyer: dict[str, Any] = snapshot.get("buyer") or {}
    customer_label = str(buyer.get("name") or buyer.get("email") or "")

    def _row(**overrides: str) -> dict[str, str]:
        row = dict.fromkeys(FEC_COLUMNS, "")
        row.update(
            {
                "JournalCode": JOURNAL_CODE,
                "JournalLib": JOURNAL_LABEL,
                "EcritureNum": invoice.invoice_number,
                "EcritureDate": entry_date,
                "PieceRef": invoice.invoice_number,
                "PieceDate": entry_date,
                "EcritureLib": label,
                "ValidDate": entry_date,
                "Idevise": invoice.currency,
                "Debit": "0,00",
                "Credit": "0,00",
            }
        )
        row.update(overrides)
        return row

    rows = [
        _row(
            CompteNum=ACCOUNT_CUSTOMER,
            CompteLib=ACCOUNT_CUSTOMER_LABEL,
            CompAuxLib=customer_label,
            Debit=_amount(invoice.total_incl_tax),
            Montantdevise=_amount(invoice.total_incl_tax),
        )
    ]

    for entry in snapshot.get("tax_breakdown") or []:
        rate = str(entry.get("rate_pct", "0"))
        rows.append(
            _row(
                CompteNum=ACCOUNT_SALES,
                CompteLib=ACCOUNT_SALES_LABEL,
                EcritureLib=f"{label} - base {rate} %",
                Credit=_amount(entry.get("base_excl_tax", "0")),
                Montantdevise=_amount(entry.get("base_excl_tax", "0")),
            )
        )
        tax_amount = Decimal(str(entry.get("tax_amount", "0")))
        # Un groupe à 0 % ne produit pas de ligne de taxe : une écriture à zéro
        # au crédit du compte de TVA n'a pas de sens comptable.
        if tax_amount > 0:
            rows.append(
                _row(
                    CompteNum=ACCOUNT_TAX,
                    CompteLib=ACCOUNT_TAX_LABEL,
                    EcritureLib=f"{label} - taxe {rate} %",
                    Credit=_amount(tax_amount),
                    Montantdevise=_amount(tax_amount),
                )
            )

    return rows


def export_invoices_to_fec(invoices: list[Invoice]) -> str:
    """Rend les factures en un fichier FEC séparé par des barres verticales."""
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=FEC_COLUMNS,
        delimiter="|",
        lineterminator="\r\n",
        quoting=csv.QUOTE_MINIMAL,
    )
    writer.writeheader()
    for invoice in invoices:
        writer.writerows(invoice_to_fec_rows(invoice))
    return buffer.getvalue()
