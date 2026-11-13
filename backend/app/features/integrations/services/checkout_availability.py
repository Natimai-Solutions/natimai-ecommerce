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

from app.features.inventory.services.availability import (
    outstanding_supplier_reservations,
)
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
    from app.core import runtime_settings

    check = await runtime_settings.get_many(
        [
            "checkout_supplier_availability_check",
            "checkout_supplier_check_timeout_seconds",
        ],
        session,
    )
    if not check["checkout_supplier_availability_check"]:
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
        if not getattr(adapter, "supports_live_availability", True):
            # A downloaded file has no live answer: its last import stands.
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
                timeout=float(check["checkout_supplier_check_timeout_seconds"]),
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

        held = await outstanding_supplier_reservations(
            session, [p.id for p in products_by_sku.values()]
        )
        for sku, data in pricing.items():
            matched = products_by_sku.get(sku)
            if matched is None:
                continue
            live = Decimal(str(data.quantity or 0))
            refreshed[sku] = live
            # The supplier still counts the units our open orders took
            # (audit 2026-11, B4): what we may sell is the rest.
            quantity = max(live - held.get(matched.id, Decimal("0")), Decimal("0"))
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


async def settle_live_supplier_quantities(
    session: AsyncSession, products: list[Product], live_by_sku: dict[str, Decimal]
) -> None:
    """Recompute, under the checkout's stock locks, what the live answer
    leaves for sale (audit 2026-11, B4).

    ``refresh_supplier_availability`` runs before the locks: a concurrent
    checkout may have reserved since. Once the rows are locked its
    reservation is committed and counted here, so its units are not sold
    again. No commit.
    """
    by_sku = {
        str(p.supplier_sku): p
        for p in products
        if _eligible(p) and str(p.supplier_sku) in live_by_sku
    }
    if not by_sku:
        return
    held = await outstanding_supplier_reservations(
        session, [p.id for p in by_sku.values()]
    )
    for sku, product in by_sku.items():
        quantity = max(
            live_by_sku[sku] - held.get(product.id, Decimal("0")), Decimal("0")
        )
        if quantity != product.supplier_quantity:
            product.supplier_quantity = quantity
            session.add(product)
