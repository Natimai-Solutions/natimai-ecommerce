"""Admin credit note endpoints (Z2): listing, PDF and accounting export.

Read-only, like the invoices they correct. A credit note is itself an issued
accounting document in a gap-free sequence: it is never edited or deleted, and
a mistake in one is corrected by yet another document.

Kept in its own module rather than folded into ``admin_invoices``: the two
sequences are legally distinct, and an accountant reconciling one of them
should never have to filter the other out of a listing.
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
from app.features.invoice.models.credit_note import CreditNote, CreditNotePublic
from app.features.invoice.services.credit_note_service import (
    credit_note_to_public,
)
from app.features.invoice.services.pdf import (
    PdfRenderingUnavailableError,
    credit_note_pdf_filename,
    render_credit_note_pdf,
)

router = APIRouter(prefix="/admin/credit-notes", tags=["admin-credit-notes"])

_EXPORT_COLUMNS = [
    "credit_note_number",
    "issued_at",
    "fiscal_year",
    "invoice_number",
    "order_number",
    "customer_name",
    "customer_email",
    "currency",
    "total_excl_tax",
    "total_tax",
    "total_incl_tax",
    "reason",
    "tax_breakdown",
]


async def _load_credit_note(
    session: SessionDep, credit_note_id: uuid.UUID
) -> CreditNote:
    credit_note = await session.get(CreditNote, credit_note_id)
    if credit_note is None:
        raise AppError(
            code="credit_note.not_found",
            status_code=404,
            message="Credit note not found",
            details={"credit_note_id": str(credit_note_id)},
        )
    return credit_note


def _csv_amount(value: Decimal) -> str:
    """French accounting software expects a comma decimal separator."""
    return str(value).replace(".", ",")


@router.get("", response_model=list[CreditNotePublic])
async def list_credit_notes(
    session: SessionDep,
    _current_user: CurrentSuperUser,
    fiscal_year: int | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[CreditNotePublic]:
    """List issued credit notes, most recent first (optionally one year)."""
    statement = select(CreditNote)
    if fiscal_year is not None:
        statement = statement.where(CreditNote.fiscal_year == fiscal_year)
    statement = (
        statement.order_by(col(CreditNote.issued_at).desc()).offset(skip).limit(limit)
    )
    result = await session.exec(statement)
    return [credit_note_to_public(note) for note in result.all()]


@router.get("/export.csv")
async def export_credit_notes_csv(
    session: SessionDep,
    _current_user: CurrentSuperUser,
    fiscal_year: int | None = None,
) -> Response:
    """Accounting export of the issued credit notes (CSV, semicolon-separated).

    Ordered by number so the accountant can check sequence continuity at a
    glance, exactly as for the invoice export.
    """
    statement = select(CreditNote)
    if fiscal_year is not None:
        statement = statement.where(CreditNote.fiscal_year == fiscal_year)
    statement = statement.order_by(col(CreditNote.credit_note_number).asc())

    result = await session.exec(statement)
    credit_notes = list(result.all())

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(_EXPORT_COLUMNS)

    for note in credit_notes:
        snapshot = note.snapshot
        buyer = snapshot.get("buyer", {})
        order_snapshot = snapshot.get("order", {})
        invoice_snapshot = snapshot.get("invoice", {})
        breakdown = " | ".join(
            f"{entry.get('rate_pct')}%:{entry.get('base_excl_tax')}"
            f"+{entry.get('tax_amount')}"
            for entry in snapshot.get("tax_breakdown", [])
        )
        writer.writerow(
            [
                note.credit_note_number,
                note.issued_at.date().isoformat(),
                note.fiscal_year,
                invoice_snapshot.get("number", ""),
                order_snapshot.get("number", ""),
                buyer.get("name", ""),
                buyer.get("email", ""),
                note.currency,
                _csv_amount(note.total_excl_tax),
                _csv_amount(note.total_tax),
                _csv_amount(note.total_incl_tax),
                note.reason or "",
                breakdown,
            ]
        )

    filename = f"avoirs-{fiscal_year}.csv" if fiscal_year is not None else "avoirs.csv"
    return Response(
        # BOM so Excel opens the accented columns in UTF-8 without prompting.
        content=buffer.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{credit_note_id}", response_model=CreditNotePublic)
async def get_credit_note(
    session: SessionDep,
    credit_note_id: uuid.UUID,
    _current_user: CurrentSuperUser,
) -> CreditNotePublic:
    """Return one issued credit note."""
    return credit_note_to_public(await _load_credit_note(session, credit_note_id))


@router.get("/{credit_note_id}/pdf")
async def download_credit_note_pdf(
    session: SessionDep,
    credit_note_id: uuid.UUID,
    _current_user: CurrentSuperUser,
) -> Response:
    """Download the PDF of an issued credit note."""
    credit_note = await _load_credit_note(session, credit_note_id)
    try:
        pdf = render_credit_note_pdf(credit_note)
    except PdfRenderingUnavailableError as exc:
        raise AppError(
            code="credit_note.pdf.unavailable",
            status_code=503,
            message="Credit note PDF rendering is unavailable on this deployment",
            details={"credit_note_id": str(credit_note_id)},
        ) from exc

    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{credit_note_pdf_filename(credit_note)}"'
            )
        },
    )
