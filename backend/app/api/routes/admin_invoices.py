"""Admin invoice endpoints (M3): listing, PDF and accounting exports.

Read-only by design — an issued invoice is never edited or deleted. A
cancelled sale is handled by a credit note (Z2), not by touching the original
document.
"""

from __future__ import annotations

import csv
import io
import uuid
from decimal import Decimal

from fastapi import APIRouter, Response
from sqlmodel import col, select

from app.api.deps import CurrentSuperUser, SessionDep
from app.core.errors import AppError
from app.features.invoice.models.invoice import (
    Invoice,
    InvoicePublic,
    InvoicesPublic,
)
from app.features.invoice.services.accounting_export import (
    export_invoices_to_fec,
)
from app.features.invoice.services.pdf import (
    PdfRenderingUnavailableError,
    invoice_pdf_filename,
    render_invoice_pdf,
)

router = APIRouter(prefix="/admin/invoices", tags=["admin-invoices"])

_EXPORT_COLUMNS = [
    "invoice_number",
    "issued_at",
    "fiscal_year",
    "order_number",
    "customer_name",
    "customer_email",
    "currency",
    "total_excl_tax",
    "total_tax",
    "total_incl_tax",
    "tax_breakdown",
]


def _to_public(invoice: Invoice) -> InvoicePublic:
    """Expose an invoice, with the order number read from its snapshot."""
    order_snapshot = invoice.snapshot.get("order", {})
    return InvoicePublic(
        id=invoice.id,
        invoice_number=invoice.invoice_number,
        fiscal_year=invoice.fiscal_year,
        order_id=invoice.order_id,
        issued_at=invoice.issued_at,
        currency=invoice.currency,
        total_excl_tax=invoice.total_excl_tax,
        total_tax=invoice.total_tax,
        total_incl_tax=invoice.total_incl_tax,
        order_number=(order_snapshot.get("number") or None),
    )


async def _load_invoice(session: SessionDep, invoice_id: uuid.UUID) -> Invoice:
    """Load an invoice or raise a 404."""
    invoice = await session.get(Invoice, invoice_id)
    if invoice is None:
        raise AppError(
            code="invoice.not_found",
            status_code=404,
            message="Invoice not found",
            details={"invoice_id": str(invoice_id)},
        )
    return invoice


@router.get("", response_model=InvoicesPublic)
async def list_invoices(
    session: SessionDep,
    _current_user: CurrentSuperUser,
    fiscal_year: int | None = None,
    skip: int = 0,
    limit: int = 100,
) -> InvoicesPublic:
    """List issued invoices, most recent first (optionally one fiscal year)."""
    statement = select(Invoice)
    if fiscal_year is not None:
        statement = statement.where(Invoice.fiscal_year == fiscal_year)
    statement = (
        statement.order_by(col(Invoice.issued_at).desc()).offset(skip).limit(limit)
    )

    result = await session.exec(statement)
    invoices = list(result.all())
    return InvoicesPublic(
        data=[_to_public(invoice) for invoice in invoices],
        count=len(invoices),
    )


@router.get("/export.csv")
async def export_invoices_csv(
    session: SessionDep,
    _current_user: CurrentSuperUser,
    fiscal_year: int | None = None,
) -> Response:
    """Accounting export of the issued invoices (CSV, semicolon-separated).

    Ordered by invoice number so the accountant can check sequence continuity
    at a glance. Amounts use a comma decimal separator, as expected by French
    accounting software.
    """
    statement = select(Invoice)
    if fiscal_year is not None:
        statement = statement.where(Invoice.fiscal_year == fiscal_year)
    statement = statement.order_by(col(Invoice.invoice_number).asc())

    result = await session.exec(statement)
    invoices = list(result.all())

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(_EXPORT_COLUMNS)

    for invoice in invoices:
        snapshot = invoice.snapshot
        buyer = snapshot.get("buyer", {})
        order_snapshot = snapshot.get("order", {})
        breakdown = " | ".join(
            f"{entry.get('rate_pct')}%:{entry.get('base_excl_tax')}"
            f"+{entry.get('tax_amount')}"
            for entry in snapshot.get("tax_breakdown", [])
        )
        writer.writerow(
            [
                invoice.invoice_number,
                invoice.issued_at.date().isoformat(),
                invoice.fiscal_year,
                order_snapshot.get("number", ""),
                buyer.get("name", ""),
                buyer.get("email", ""),
                invoice.currency,
                _csv_amount(invoice.total_excl_tax),
                _csv_amount(invoice.total_tax),
                _csv_amount(invoice.total_incl_tax),
                breakdown,
            ]
        )

    filename = (
        f"factures-{fiscal_year}.csv" if fiscal_year is not None else "factures.csv"
    )
    return Response(
        # BOM so Excel opens the accented columns in UTF-8 without prompting.
        content=buffer.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export-fec.txt")
async def export_invoices_fec(
    session: SessionDep,
    _current_user: CurrentSuperUser,
    fiscal_year: int | None = None,
) -> Response:
    """Export au format FEC — écritures comptables importables.

    Complémentaire de ``/export.csv`` et non redondant : le CSV liste les
    factures à plat pour contrôler la continuité de la numérotation, tandis que
    celui-ci produit le journal de ventes en écritures équilibrées, tel que les
    logiciels comptables l'attendent.

    Encodage ISO-8859-15 comme le veut la spécification, avec repli sur les
    caractères translittérables : un nom de client exotique ne doit pas faire
    échouer tout l'export.
    """
    statement = select(Invoice)
    if fiscal_year is not None:
        statement = statement.where(Invoice.fiscal_year == fiscal_year)
    statement = statement.order_by(col(Invoice.invoice_number).asc())

    result = await session.exec(statement)
    invoices = list(result.all())

    payload = export_invoices_to_fec(invoices)
    filename = f"FEC-{fiscal_year}.txt" if fiscal_year is not None else "FEC.txt"
    return Response(
        content=payload.encode("iso-8859-15", errors="replace"),
        media_type="text/plain; charset=iso-8859-15",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _csv_amount(value: Decimal) -> str:
    """Format an amount for the accounting export (comma decimal separator)."""
    return str(value).replace(".", ",")


@router.get("/{invoice_id}", response_model=InvoicePublic)
async def get_invoice(
    session: SessionDep,
    invoice_id: uuid.UUID,
    _current_user: CurrentSuperUser,
) -> InvoicePublic:
    """Return one invoice's metadata."""
    return _to_public(await _load_invoice(session, invoice_id))


@router.get("/{invoice_id}/pdf")
async def download_invoice_pdf(
    session: SessionDep,
    invoice_id: uuid.UUID,
    _current_user: CurrentSuperUser,
) -> Response:
    """Download an invoice PDF."""
    invoice = await _load_invoice(session, invoice_id)
    try:
        pdf = render_invoice_pdf(invoice)
    except PdfRenderingUnavailableError as exc:
        raise AppError(
            code="invoice.pdf.unavailable",
            status_code=503,
            message="Invoice PDF rendering is unavailable on this deployment",
            details={"invoice_id": str(invoice_id)},
        ) from exc

    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{invoice_pdf_filename(invoice)}"'
            )
        },
    )
