"""Re-check supplier availability at checkout, against the supplier itself.

``product.supplier_quantity`` is a snapshot refreshed by a cron every two
hours. The checkout used to reserve against it and nothing else, so on
drop-shipped stock a two-hour window separated what the customer was told from
what the supplier actually had. On fast-moving references that is a structural
oversell: the order is taken, paid, and only then found to be unfulfillable.

One call per checkout, for the supplier-managed lines only — negligible
against the sync quota, and it happens once per order rather than once per
page view.

**It never blocks a sale on a supplier outage.** If the supplier cannot be
reached the snapshot stands, because refusing every order while Ingram is
having a bad afternoon is worse than the oversell risk this reduces. The
refusal only happens when the supplier answers and says the stock is not
there.
"""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.features.product.models.product import Product
from app.services.suppliers import resolve_adapter

logger = logging.getLogger(__name__)


def _eligible(product: Product) -> bool:
    """Only supplier-managed lines with a supplier and a SKU are checked.

    Whether that supplier has a live API is decided per supplier below
    (manual and file suppliers have none: their snapshot stands). Read
    defensively: this runs on the checkout path — it must never be the
    thing that raises.
    """
    return bool(
        getattr(product, "is_supplier_managed", False)
        and getattr(product, "supplier_name", None)
        and getattr(product, "supplier_sku", None)
    )


async def refresh_supplier_availability(
    session: AsyncSession, products: list[Product]
) -> dict[str, Decimal]:
    """Refresh ``supplier_quantity`` from the supplier for ``products``.

    Returns the quantities actually obtained, keyed by SKU — empty when the
    check is disabled, when no line is eligible, or when the supplier could not
    be reached. Does not commit: the caller owns the checkout transaction.
    """
    if not settings.CHECKOUT_SUPPLIER_AVAILABILITY_CHECK:
        return {}

    by_supplier: dict[str, dict[str, Product]] = {}
    for product in products:
        if not _eligible(product):
            continue
        by_supplier.setdefault(str(product.supplier_name), {})[
            str(product.supplier_sku)
        ] = product

    if not by_supplier:
        return {}

    refreshed: dict[str, Decimal] = {}
    for supplier_name, products_by_sku in by_supplier.items():
        try:
            adapter = await resolve_adapter(session, supplier_name)
        except Exception as exc:  # noqa: BLE001 - never fail the checkout
            logger.warning(
                "Checkout availability check skipped: cannot resolve %s (%s)",
                supplier_name,
                exc,
            )
            continue
        if adapter is None:
            logger.debug(
                "Checkout availability check skipped: %s has no live API",
                supplier_name,
            )
            continue
        if not adapter.is_configured():
            logger.debug(
                "Checkout availability check skipped: %s is not configured",
                supplier_name,
            )
            continue
        if not adapter.is_sync_enabled():
            # A supplier whose syncs were switched off is not called either:
            # the admin turned it off, the snapshot stands.
            logger.debug(
                "Checkout availability check skipped: %s has syncs disabled",
                supplier_name,
            )
            continue

        try:
            pricing = await asyncio.wait_for(
                adapter.fetch_price_and_availability(list(products_by_sku)),
                timeout=settings.CHECKOUT_SUPPLIER_CHECK_TIMEOUT_SECONDS,
            )
        except Exception as exc:  # noqa: BLE001
            # Deliberately broad and deliberately non-fatal: the checkout must
            # survive anything the supplier client can throw, including the
            # TimeoutError raised by wait_for above.
            logger.warning(
                "Checkout availability check against %s failed (%s) — falling "
                "back to the last synced quantities",
                supplier_name,
                exc,
            )
            continue

        for sku, data in pricing.items():
            matched = products_by_sku.get(sku)
            if matched is None:
                continue
            quantity = Decimal(str(data.quantity or 0))
            refreshed[sku] = quantity
            if quantity != matched.supplier_quantity:
                logger.info(
                    "Checkout availability: %s moved from %s to %s since the last sync",
                    sku,
                    matched.supplier_quantity,
                    quantity,
                )
                matched.supplier_quantity = quantity
                session.add(matched)

        missing = set(products_by_sku) - set(pricing)
        if missing:
            # The supplier no longer knows these SKUs. Treat them as out of
            # stock for this checkout; the delisting sweep decides whether they
            # leave the catalogue for good.
            for sku in missing:
                stale = products_by_sku[sku]
                logger.warning(
                    "Checkout availability: %s no longer returned by %s — "
                    "treating as out of stock",
                    sku,
                    supplier_name,
                )
                refreshed[sku] = Decimal("0")
                stale.supplier_quantity = Decimal("0")
                session.add(stale)

    return refreshed
