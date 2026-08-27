"""Customer-facing invoice endpoints (authenticated user — own invoices only).

Phase 5a / M3: listing and PDF download of the invoices issued for the
customer's paid orders.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response
from sqlmodel import col, select

from app.api.deps import CurrentUser, SessionDep
from app.core.errors import AppError
from app.features.invoice.models.invoice import (
    Invoice,
    InvoicePublic,
    InvoicesPublic,
)
from app.features.invoice.services.pdf import (
    PdfRenderingUnavailableError,
    invoice_pdf_filename,
    render_invoice_pdf,
)
from app.features.order.models.order import Order

router = APIRouter(prefix="/invoices", tags=["invoice"])


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


async def _load_own_invoice(
    session: SessionDep, *, invoice_id: uuid.UUID, user_id: uuid.UUID
) -> Invoice:
    """Load an invoice owned by ``user_id``.

    A foreign invoice is reported as missing so ids cannot be probed.
    """
    invoice = await session.get(Invoice, invoice_id)
    if invoice is None or invoice.user_id != user_id:
        raise AppError(
            code="invoice.not_found",
            status_code=404,
            message="Invoice not found",
            details={"invoice_id": str(invoice_id)},
        )
    return invoice


@router.get("/me", response_model=InvoicesPublic)
async def list_my_invoices(
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 50,
) -> InvoicesPublic:
    """List the authenticated customer's invoices, most recent first."""
    statement = (
        select(Invoice)
        .where(Invoice.user_id == current_user.id)
        .order_by(col(Invoice.issued_at).desc())
        .offset(skip)
        .limit(limit)
    )
    result = await session.exec(statement)
    invoices = list(result.all())
    return InvoicesPublic(
        data=[_to_public(invoice) for invoice in invoices],
        count=len(invoices),
    )


@router.get("/me/by-order/{order_id}", response_model=InvoicePublic)
async def get_my_invoice_for_order(
    session: SessionDep,
    order_id: uuid.UUID,
    current_user: CurrentUser,
) -> InvoicePublic:
    """Return the invoice issued for one of the customer's orders."""
    order = await session.get(Order, order_id)
    if order is None or order.user_id != current_user.id:
        raise AppError(
            code="invoice.order_not_found",
            status_code=404,
            message="Order not found",
            details={"order_id": str(order_id)},
        )

    result = await session.exec(select(Invoice).where(Invoice.order_id == order_id))
    invoice = result.first()
    if invoice is None:
        raise AppError(
            code="invoice.not_issued",
            status_code=404,
            message="No invoice issued for this order yet",
            details={"order_id": str(order_id)},
        )
    return _to_public(invoice)


@router.get("/me/{invoice_id}/pdf")
async def download_my_invoice_pdf(
    session: SessionDep,
    invoice_id: uuid.UUID,
    current_user: CurrentUser,
) -> Response:
    """Download the PDF of one of the customer's invoices."""
    invoice = await _load_own_invoice(
        session, invoice_id=invoice_id, user_id=current_user.id
    )
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
