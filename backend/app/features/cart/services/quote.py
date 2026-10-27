"""Issuing a quote (« devis ») from a quote request, and turning it into an
order.

The request is what the customer sent and is never edited. The quote is the
admin's answer: the lines at the price granted, the delivery fee, a validity
date, a message — frozen in ``QuoteRequest.quote_snapshot`` under a
``DEV-AAAA-NNNNN`` number, rendered as a PDF on demand and e-mailed to the
customer. Until ``valid_until`` the customer converts it into an order from
their account: the checkout then bills the quoted prices, not the catalogue.
"""

from __future__ import annotations

import functools
import logging
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import anyio
from fastapi import Response
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core import runtime_settings
from app.core.config import settings
from app.core.errors import AppError
from app.features.cart.models.quote_request import QuoteRequest, QuoteRequestStatus
from app.features.invoice.services.invoice_service import _seller_identity
from app.features.invoice.services.numbering import allocate_quote_number
from app.features.invoice.services.pdf import (
    PdfRenderingUnavailableError,
    quote_pdf_filename,
    render_quote_pdf,
)
from app.features.notification.email_renderer import render_email
from app.features.notification.mailer import send_email
from app.features.product.models.product import Product
from app.utils.money import quantize_amount

logger = logging.getLogger(__name__)

#: Default validity of a quote, from its issue date.
QUOTE_VALIDITY_DAYS = 30


class QuoteLine(BaseModel):
    """A line of the quote as the admin grants it."""

    product_id: uuid.UUID | None = None
    product_name: str = Field(max_length=255)
    quantity: int = Field(ge=1)
    unit_price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)


class QuoteIssueBody(BaseModel):
    """What the admin fills in to issue (or re-issue) the quote."""

    lines: list[QuoteLine] = Field(min_length=1)
    shipping_fee_amount: Decimal = Field(
        default=Decimal("0.00"), ge=0, max_digits=12, decimal_places=2
    )
    valid_until: date | None = None
    customer_message: str | None = Field(default=None, max_length=2000)
    send_email: bool = True


def proposed_lines(quote: QuoteRequest) -> list[QuoteLine]:
    """The request's cart as quote lines: the admin's starting point."""
    snapshot = quote.items_snapshot or {}
    items = snapshot.get("items") if isinstance(snapshot, dict) else None
    lines: list[QuoteLine] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        try:
            product_id = (
                uuid.UUID(str(item["product_id"])) if item.get("product_id") else None
            )
        except ValueError:
            product_id = None
        lines.append(
            QuoteLine(
                product_id=product_id,
                product_name=str(item.get("product_name") or "Article"),
                quantity=max(1, int(Decimal(str(item.get("quantity") or 1)))),
                unit_price=Decimal(str(item.get("unit_price") or 0)),
            )
        )
    return lines


def quote_currency(quote: QuoteRequest) -> str:
    snapshot = quote.items_snapshot or {}
    return str(snapshot.get("currency") or settings.REFERENCE_CURRENCY)


async def issue_quote(
    session: AsyncSession, quote: QuoteRequest, body: QuoteIssueBody
) -> QuoteRequest:
    """Freeze the quote: number (kept on a re-issue), lines, totals, validity,
    seller and buyer blocks. Status « quoted ». Flushes, no commit."""
    currency = quote_currency(quote)
    now = datetime.now(UTC)
    if not quote.quote_number:
        quote.quote_number = await allocate_quote_number(session, fiscal_year=now.year)
    references: dict[uuid.UUID, str] = {}
    for line in body.lines:
        if line.product_id and line.product_id not in references:
            product = await session.get(Product, line.product_id)
            references[line.product_id] = (
                getattr(product, "vendor_part_number", None) or ""
            )
    lines: list[dict[str, Any]] = []
    subtotal = Decimal("0.00")
    for line in body.lines:
        line_total = quantize_amount(line.unit_price * line.quantity, currency)
        subtotal += line_total
        lines.append(
            {
                "product_id": str(line.product_id) if line.product_id else None,
                "product_name": line.product_name,
                "reference": references.get(line.product_id) if line.product_id else "",
                "quantity": line.quantity,
                "unit_price": str(quantize_amount(line.unit_price, currency)),
                "line_total": str(line_total),
            }
        )
    shipping = quantize_amount(body.shipping_fee_amount, currency)
    valid_until = body.valid_until or (now.date() + timedelta(days=QUOTE_VALIDITY_DAYS))
    quote.quote_snapshot = {
        "quote_number": quote.quote_number,
        "issued_at": now.strftime("%d/%m/%Y"),
        "valid_until": valid_until.strftime("%d/%m/%Y"),
        "currency": currency,
        "seller": await _seller_identity(session),
        "buyer": {
            "name": quote.full_name or "",
            "email": quote.email,
            "phone": quote.phone or "",
            "address": quote.shipping_address or "",
        },
        "lines": lines,
        "shipping_fee_amount": str(shipping),
        "subtotal_amount": str(quantize_amount(subtotal, currency)),
        "total_amount": str(quantize_amount(subtotal + shipping, currency)),
        "customer_message": (body.customer_message or "").strip(),
        "accept_url": f"{settings.FRONTEND_HOST.rstrip('/')}/mon-compte?tab=quotes",
    }
    quote.quoted_at = now
    quote.valid_until = valid_until
    quote.status = QuoteRequestStatus.QUOTED.value
    quote.handled_at = None
    quote.handled_by_id = None
    session.add(quote)
    await session.flush()
    return quote


async def send_quote_email(session: AsyncSession, quote: QuoteRequest) -> bool:
    """E-mail the quote to the customer, PDF attached when it can be
    rendered (the text carries the amounts and the link either way)."""
    snapshot = quote.quote_snapshot or {}
    email = render_email(
        "quote_issued",
        full_name=quote.full_name or "client",
        quote_number=quote.quote_number or "",
        valid_until=snapshot.get("valid_until", ""),
        total_amount=snapshot.get("total_amount", ""),
        currency=snapshot.get("currency", ""),
        customer_message=snapshot.get("customer_message", ""),
        accept_url=snapshot.get("accept_url", ""),
        has_account=quote.user_id is not None,
        shop_name=runtime_settings.peek("shop_name"),
    )
    attachments: list[tuple[str, bytes, str]] = []
    try:
        attachments.append(
            (quote_pdf_filename(quote), render_quote_pdf(quote), "application/pdf")
        )
    except PdfRenderingUnavailableError as exc:
        logger.warning("Quote %s e-mailed without PDF: %s", quote.quote_number, exc)
    result = await send_email(
        session,
        recipient=quote.email,
        subject=email.subject,
        text=email.text,
        html=email.html,
        event_type="quote.issued",
        metadata={"quote_request_id": str(quote.id)},
        attachments=attachments or None,
    )
    if not result.delivered:
        logger.warning("Quote %s e-mail failed: %s", quote.quote_number, result.error)
    return bool(result.delivered)


def check_convertible(quote: QuoteRequest, *, user: Any) -> None:
    """A quote turns into an order only for its customer, while it is
    issued, valid, not converted yet, and made of catalogue products."""
    owned = quote.user_id == user.id or (
        quote.user_id is None and quote.email.lower() == str(user.email).lower()
    )
    if not owned:
        raise AppError(
            code="quote.not_found",
            status_code=404,
            message="Devis introuvable",
            details={"quote_request_id": str(quote.id)},
        )
    details = {"quote_request_id": str(quote.id), "status": quote.status}
    if quote.status != QuoteRequestStatus.QUOTED.value or not quote.quote_snapshot:
        raise AppError(
            code="quote.not_issued",
            status_code=409,
            message="Ce devis n'est pas (ou plus) proposé à la commande",
            details=details,
        )
    if quote.order_id is not None:
        raise AppError(
            code="quote.already_converted",
            status_code=409,
            message="Ce devis a déjà été transformé en commande",
            details={**details, "order_id": str(quote.order_id)},
        )
    if quote.valid_until is not None and quote.valid_until < date.today():
        raise AppError(
            code="quote.expired",
            status_code=409,
            message=f"Ce devis a expiré le {quote.valid_until.strftime('%d/%m/%Y')}",
            details={**details, "valid_until": quote.valid_until.isoformat()},
        )
    if any(
        not line.get("product_id") for line in quote.quote_snapshot.get("lines", [])
    ):
        raise AppError(
            code="quote.not_orderable",
            status_code=409,
            message="Ce devis contient des lignes hors catalogue : contactez-nous",
            details=details,
        )


def quoted_prices(quote: QuoteRequest) -> dict[uuid.UUID, tuple[int, Decimal]]:
    """``{product_id: (quantity, unit_price)}`` of an issued quote."""
    out: dict[uuid.UUID, tuple[int, Decimal]] = {}
    for line in (quote.quote_snapshot or {}).get("lines", []):
        if line.get("product_id"):
            pid = uuid.UUID(str(line["product_id"]))
            qty, price = int(line["quantity"]), Decimal(str(line["unit_price"]))
            previous = out.get(pid)
            out[pid] = (qty + previous[0], price) if previous else (qty, price)
    return out


async def quote_pdf_response(quote: QuoteRequest) -> Response:
    """The issued quote as a PDF download (admin and customer routes)."""
    if not quote.quote_snapshot:
        raise AppError(
            code="quote.not_issued",
            status_code=409,
            message="Ce devis n'a pas encore été émis",
            details={"quote_request_id": str(quote.id)},
        )
    from app.core.i18n import request_locale

    try:
        # The customer downloads it in the language of the interface (R7).
        pdf = await anyio.to_thread.run_sync(
            functools.partial(render_quote_pdf, quote, lang=request_locale())
        )
    except PdfRenderingUnavailableError as exc:
        raise AppError(
            code="quote.pdf.unavailable",
            status_code=503,
            message="Le rendu PDF est indisponible sur ce serveur",
            details={"reason": str(exc)},
        ) from exc
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{quote_pdf_filename(quote)}"'
        },
    )


__all__ = [
    "QUOTE_VALIDITY_DAYS",
    "QuoteIssueBody",
    "QuoteLine",
    "check_convertible",
    "issue_quote",
    "proposed_lines",
    "quote_currency",
    "quote_pdf_response",
    "quoted_prices",
    "send_quote_email",
]
