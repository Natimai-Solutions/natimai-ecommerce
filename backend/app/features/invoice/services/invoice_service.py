"""Invoice issuance (M3).

An invoice is issued once a payment is captured. Issuance is idempotent (one
invoice per order) and freezes everything the document shows into
``Invoice.snapshot``.

Tax handling — the prices stored on ``OrderLine.unit_price`` are **tax
inclusive** (``calculate_sale_price`` multiplies by ``1 + tax_rate``), so the
invoice works backwards from the amount actually charged:

    HT = TTC / (1 + taux)      taxe = TTC - HT

The ventilation is computed **per rate group**, which guarantees the printed
breakdown adds up exactly to the order total the customer paid: rounding
happens once per group, and the tax is the remainder rather than a second
independent rounding.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.features.invoice.models.invoice import Invoice
from app.features.invoice.services.numbering import allocate_invoice_number
from app.features.order.models.order import Order
from app.features.order.models.order_line import OrderLine
from app.features.payment.models.payment import Payment
from app.features.product.models.product import Product
from app.features.product.models.tax_rate import TaxRate
from app.features.user.models.address import Address
from app.features.user.models.user import User
from app.utils.money import quantize_amount

logger = logging.getLogger(__name__)

_ZERO = Decimal("0.00")


class InvoiceIssuanceError(RuntimeError):
    """Raised when an invoice cannot be issued for an order."""


async def get_invoice_for_order(
    session: AsyncSession, *, order_id: uuid.UUID
) -> Invoice | None:
    """Return the invoice already issued for ``order_id``, if any."""
    result = await session.exec(select(Invoice).where(Invoice.order_id == order_id))
    return result.first()


async def _resolve_order_currency(session: AsyncSession, order: Order) -> str:
    """Currency the order was billed in.

    ``Order.currency`` is set at checkout; orders predating that column fall
    back to the currency of their payment, then to the reference currency.
    """
    if order.currency:
        return order.currency

    result = await session.exec(
        select(Payment).where(Payment.order_id == order.id).limit(1)
    )
    payment = result.first()
    if payment is not None and payment.currency:
        return str(payment.currency)
    return settings.REFERENCE_CURRENCY


async def _resolve_fees_tax_rate_pct(session: AsyncSession) -> Decimal:
    """Rate applied to shipping/payment fees for the tax breakdown.

    Falls back to 0 % when the configured code has no active rate — the
    invoice then shows the fees untaxed, which is visible on the document
    rather than silently wrong in the totals.
    """
    statement = (
        select(TaxRate)
        .where(
            TaxRate.code == settings.INVOICE_FEES_TAX_CODE,
            col(TaxRate.is_active).is_(True),
        )
        .order_by(col(TaxRate.valid_from).desc())
        .limit(1)
    )
    result = await session.exec(statement)
    tax_rate = result.first()
    if tax_rate is None:
        logger.warning(
            "No active TaxRate '%s' — invoice fees will be reported untaxed",
            settings.INVOICE_FEES_TAX_CODE,
        )
        return _ZERO
    return Decimal(str(tax_rate.rate_pct))


def _split_incl_tax(
    amount_incl: Decimal, rate_pct: Decimal, currency: str
) -> tuple[Decimal, Decimal]:
    """Split a tax-inclusive amount into ``(excl_tax, tax)``.

    The tax is the remainder so that ``excl + tax == incl`` always holds.
    """
    divisor = Decimal("1") + (rate_pct / Decimal("100"))
    excl = quantize_amount(amount_incl / divisor, currency)
    return excl, amount_incl - excl


def _seller_identity() -> dict[str, str]:
    """Seller block printed on the invoice, from configuration."""
    identity = {
        "name": settings.INVOICE_SELLER_NAME,
        "address": settings.INVOICE_SELLER_ADDRESS,
        "registration": settings.INVOICE_SELLER_REGISTRATION,
        "email": settings.INVOICE_SELLER_EMAIL,
        "phone": settings.INVOICE_SELLER_PHONE,
        "legal_footer": settings.INVOICE_LEGAL_FOOTER,
    }
    missing = [key for key in ("address", "registration") if not identity[key]]
    if missing:
        logger.warning(
            "Invoice seller identity incomplete (%s not configured) — the "
            "issued document is not legally compliant. Set INVOICE_SELLER_* "
            "in the environment.",
            ", ".join(f"INVOICE_SELLER_{key.upper()}" for key in missing),
        )
    return identity


async def _build_buyer_identity(
    session: AsyncSession, *, order: Order, user: User | None
) -> dict[str, Any]:
    """Buyer block: account identity plus the shipping address of the order."""
    billing_address = order.shipping_address or ""
    if not billing_address:
        # Fall back to the user's first known address (orders placed through
        # flows that do not copy the address into the order).
        result = await session.exec(
            select(Address).where(Address.user_id == order.user_id).limit(1)
        )
        address = result.first()
        if address is not None:
            billing_address = ", ".join(
                part
                for part in (
                    address.street,
                    address.postal_code,
                    address.city,
                    address.country,
                )
                if part
            )

    return {
        "name": (user.full_name if user else None) or "",
        "email": (user.email if user else None) or "",
        "address": billing_address,
    }


async def _build_lines_snapshot(
    session: AsyncSession, *, order: Order, currency: str
) -> tuple[list[dict[str, Any]], dict[str, Decimal]]:
    """Return the invoice lines and the tax-inclusive total per rate.

    Rates are keyed by their string form so the mapping survives the JSON
    round-trip in ``Invoice.snapshot``.
    """
    result = await session.exec(select(OrderLine).where(OrderLine.order_id == order.id))
    order_lines = list(result.all())

    lines: list[dict[str, Any]] = []
    incl_by_rate: dict[str, Decimal] = {}

    for order_line in order_lines:
        product = await session.get(Product, order_line.product_id)
        tax_rate = (
            await session.get(TaxRate, order_line.tax_rate_id)
            if order_line.tax_rate_id
            else None
        )
        rate_pct = Decimal(str(tax_rate.rate_pct)) if tax_rate is not None else _ZERO

        line_incl = quantize_amount(
            order_line.unit_price * order_line.quantity, currency
        )
        excl, tax = _split_incl_tax(line_incl, rate_pct, currency)

        lines.append(
            {
                "description": (
                    getattr(product, "name", None) or f"Produit {order_line.product_id}"
                ),
                "reference": getattr(product, "vendor_part_number", None) or "",
                "quantity": order_line.quantity,
                "unit_price_incl_tax": str(order_line.unit_price),
                "total_incl_tax": str(line_incl),
                "total_excl_tax": str(excl),
                "tax_amount": str(tax),
                "tax_rate_pct": str(rate_pct),
                "tax_label": tax_rate.label if tax_rate is not None else "",
            }
        )
        key = str(rate_pct)
        incl_by_rate[key] = incl_by_rate.get(key, _ZERO) + line_incl

    return lines, incl_by_rate


async def build_invoice_snapshot(
    session: AsyncSession, *, order: Order, user: User | None
) -> dict[str, Any]:
    """Build the immutable snapshot printed on the invoice."""
    currency = await _resolve_order_currency(session, order)
    lines, incl_by_rate = await _build_lines_snapshot(
        session, order=order, currency=currency
    )

    lines_incl_total = sum(incl_by_rate.values(), _ZERO)
    fees_rate_pct = await _resolve_fees_tax_rate_pct(session)

    # The order total is what the customer actually paid: it is authoritative.
    # Reconcile any drift between the line sum and the stored subtotal onto the
    # fees rate group so the invoice always balances against the order.
    subtotal_drift = quantize_amount(order.subtotal_amount, currency) - quantize_amount(
        lines_incl_total, currency
    )
    if subtotal_drift != _ZERO:
        logger.warning(
            "Order %s: line sum (%s) differs from stored subtotal (%s) — "
            "difference carried on the fees tax group so the invoice balances",
            order.id,
            lines_incl_total,
            order.subtotal_amount,
        )

    fees_incl = quantize_amount(
        order.shipping_fee_amount + order.payment_fee_amount + subtotal_drift,
        currency,
    )
    fees_key = str(fees_rate_pct)
    if fees_incl != _ZERO:
        incl_by_rate[fees_key] = incl_by_rate.get(fees_key, _ZERO) + fees_incl

    tax_breakdown: list[dict[str, str]] = []
    total_excl = _ZERO
    total_tax = _ZERO
    for rate_key in sorted(incl_by_rate, key=lambda value: Decimal(value)):
        incl = quantize_amount(incl_by_rate[rate_key], currency)
        if incl == _ZERO:
            continue
        excl, tax = _split_incl_tax(incl, Decimal(rate_key), currency)
        total_excl += excl
        total_tax += tax
        tax_breakdown.append(
            {
                "rate_pct": rate_key,
                "base_excl_tax": str(excl),
                "tax_amount": str(tax),
                "total_incl_tax": str(incl),
            }
        )

    total_incl = quantize_amount(total_excl + total_tax, currency)
    order_total = quantize_amount(order.total_amount, currency)
    if total_incl != order_total:
        # Should not happen (the drift above absorbs line/subtotal mismatches);
        # refuse to issue rather than print a document that does not tie out.
        raise InvoiceIssuanceError(
            f"Invoice total {total_incl} does not match order total {order_total} "
            f"for order {order.id}"
        )

    return {
        "seller": _seller_identity(),
        "buyer": await _build_buyer_identity(session, order=order, user=user),
        "order": {
            "id": str(order.id),
            "number": order.order_number or "",
            "delivery_type": order.delivery_type or "",
        },
        "currency": currency,
        "lines": lines,
        "fees": {
            "shipping_incl_tax": str(
                quantize_amount(order.shipping_fee_amount, currency)
            ),
            "payment_incl_tax": str(
                quantize_amount(order.payment_fee_amount, currency)
            ),
            "tax_rate_pct": str(fees_rate_pct),
        },
        "tax_breakdown": tax_breakdown,
        "totals": {
            "excl_tax": str(total_excl),
            "tax": str(total_tax),
            "incl_tax": str(total_incl),
        },
    }


async def issue_invoice_for_order(
    session: AsyncSession,
    *,
    order_id: uuid.UUID,
    issued_at: datetime | None = None,
    commit: bool = True,
) -> Invoice:
    """Issue the invoice for a paid order (idempotent).

    Returns the existing invoice when the order already has one, so a replayed
    ``payment.captured`` event never produces a duplicate accounting document.
    """
    existing = await get_invoice_for_order(session, order_id=order_id)
    if existing is not None:
        logger.info(
            "Invoice %s already issued for order %s — reusing",
            existing.invoice_number,
            order_id,
        )
        return existing

    order = await session.get(Order, order_id)
    if order is None:
        raise InvoiceIssuanceError(f"Order {order_id} not found")

    user = await session.get(User, order.user_id)
    issuance_date = issued_at or datetime.now(timezone.utc)
    snapshot = await build_invoice_snapshot(session, order=order, user=user)

    invoice_number, sequence_number = await allocate_invoice_number(
        session, fiscal_year=issuance_date.year
    )

    totals = snapshot["totals"]
    invoice = Invoice(
        invoice_number=invoice_number,
        fiscal_year=issuance_date.year,
        sequence_number=sequence_number,
        order_id=order.id,
        user_id=order.user_id,
        issued_at=issuance_date,
        currency=snapshot["currency"],
        total_excl_tax=Decimal(totals["excl_tax"]),
        total_tax=Decimal(totals["tax"]),
        total_incl_tax=Decimal(totals["incl_tax"]),
        snapshot=snapshot,
    )
    session.add(invoice)

    if commit:
        await session.commit()
        await session.refresh(invoice)

    logger.info(
        "Invoice %s issued for order %s (%s %s)",
        invoice_number,
        order_id,
        totals["incl_tax"],
        snapshot["currency"],
    )
    return invoice
