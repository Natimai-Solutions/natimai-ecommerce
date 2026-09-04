"""Invoice PDF rendering (M3) — Jinja2 HTML → WeasyPrint.

The PDF is rendered **on demand from** ``Invoice.snapshot``, never from live
catalogue/tax data: the snapshot is frozen at issuance, so re-rendering an old
invoice reproduces the original document.

WeasyPrint is imported lazily. It needs system libraries (pango, cairo,
gdk-pixbuf) that are installed in the backend image but usually absent on a
Windows dev machine — a missing library must therefore break PDF rendering
only, never invoice issuance, the API startup or the test suite.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.features.invoice.models.credit_note import CreditNote
from app.features.invoice.models.invoice import Invoice

# app/features/invoice/services/pdf.py → app/templates/invoice
_TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "templates" / "invoice"

DEFAULT_LANG = "fr"


class PdfRenderingUnavailableError(RuntimeError):
    """Raised when WeasyPrint (or its system libraries) cannot be loaded."""


# French typography, spelled out so an editor cannot silently mangle them:
# narrow no-break space between thousands, no-break space before the currency.
_THOUSANDS_SEPARATOR = "\u202f"
_CURRENCY_SEPARATOR = "\u00a0"


def _format_amount(value: Any, currency: str = "") -> str:
    """Render an amount in French convention (``472 700 XPF`` (espaces insécables)).

    XPF has no minor unit, so its amounts are printed without decimals.
    """
    try:
        amount = Decimal(str(value))
    except Exception:  # noqa: BLE001 — templates must never crash on bad data
        return str(value)

    quantized = amount.quantize(Decimal("1")) if currency == "XPF" else amount
    sign = "-" if quantized < 0 else ""
    digits = f"{abs(quantized):,.0f}" if currency == "XPF" else f"{abs(quantized):,.2f}"
    formatted = digits.replace(",", _THOUSANDS_SEPARATOR).replace(".", ",")
    if not currency:
        return f"{sign}{formatted}"
    return f"{sign}{formatted}{_CURRENCY_SEPARATOR}{currency}"


_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)
_env.filters["amount"] = _format_amount


def render_invoice_html(invoice: Invoice, *, lang: str = DEFAULT_LANG) -> str:
    """Render the invoice HTML from its frozen snapshot."""
    template = _env.get_template(f"{lang}/invoice.html")
    # Snapshot first, then the columns that are authoritative on the row
    # (they also live in the snapshot; the persisted values win).
    context: dict[str, Any] = dict(invoice.snapshot)
    context.update(
        invoice_number=invoice.invoice_number,
        issued_at=invoice.issued_at,
        currency=invoice.currency,
        totals={
            "excl_tax": invoice.total_excl_tax,
            "tax": invoice.total_tax,
            "incl_tax": invoice.total_incl_tax,
        },
    )
    return template.render(**context)


def render_invoice_pdf(invoice: Invoice, *, lang: str = DEFAULT_LANG) -> bytes:
    """Render the invoice as a PDF document.

    Raises ``PdfRenderingUnavailableError`` when WeasyPrint is not importable,
    so callers can return a clean error instead of a 500 stack trace.
    """
    html = render_invoice_html(invoice, lang=lang)
    try:
        from weasyprint import HTML  # noqa: PLC0415 — lazy on purpose
    except Exception as exc:  # noqa: BLE001 — missing lib or missing system deps
        raise PdfRenderingUnavailableError(
            "WeasyPrint is unavailable in this environment "
            "(package or system libraries missing): "
            f"{exc}"
        ) from exc

    return bytes(HTML(string=html).write_pdf())


def invoice_pdf_filename(invoice: Invoice) -> str:
    """Download filename for an invoice PDF."""
    return f"{invoice.invoice_number}.pdf"


def render_credit_note_html(
    credit_note: CreditNote, *, lang: str = DEFAULT_LANG
) -> str:
    """Render the credit note HTML from its frozen snapshot."""
    template = _env.get_template(f"{lang}/credit_note.html")
    context: dict[str, Any] = dict(credit_note.snapshot)
    context.update(
        credit_note_number=credit_note.credit_note_number,
        issued_at=credit_note.issued_at,
        currency=credit_note.currency,
        totals={
            "excl_tax": credit_note.total_excl_tax,
            "tax": credit_note.total_tax,
            "incl_tax": credit_note.total_incl_tax,
        },
    )
    return template.render(**context)


def render_credit_note_pdf(
    credit_note: CreditNote, *, lang: str = DEFAULT_LANG
) -> bytes:
    """Render the credit note as a PDF document.

    Same lazy WeasyPrint import as the invoice: a missing system library must
    cost the PDF only, never the issuance of the accounting document.
    """
    html = render_credit_note_html(credit_note, lang=lang)
    try:
        from weasyprint import HTML  # noqa: PLC0415 — lazy on purpose
    except Exception as exc:  # noqa: BLE001 — missing lib or missing system deps
        raise PdfRenderingUnavailableError(
            "WeasyPrint is unavailable in this environment "
            "(package or system libraries missing): "
            f"{exc}"
        ) from exc

    return bytes(HTML(string=html).write_pdf())


def credit_note_pdf_filename(credit_note: CreditNote) -> str:
    """Download filename for a credit note PDF."""
    return f"{credit_note.credit_note_number}.pdf"
