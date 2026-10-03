"""Attach a manual product to its supplier now, or detach it (R4 / S8).

A product typed by hand and linked to a supplier (``supplier_name`` +
``supplier_sku``) used to be adopted **passively**: only when the next file
import or catalog sync happened to carry that reference. An Ingram reference
outside the synced categories was therefore never adopted.

* :func:`attach_now` asks the supplier's API for that one reference and
  adopts the product on the spot (cost, currency, stock, mapping), keeping
  every content field the admin wrote (locked, as a passive adoption does).
  A file supplier has no API: the link is recorded and the product is adopted
  by the next import that carries the reference.
* :func:`detach` turns a supplier-managed product back into a manual one:
  no more syncs, the admin's locks stay, the supplier stock no longer counts.

Neither commits: the route owns the transaction.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlmodel import col, delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.errors import AppError
from app.features.integrations.models.supplier import Supplier
from app.features.integrations.models.supplier_sync import SupplierProductMapping
from app.features.integrations.services.file_import_run import (
    orchestrator_for_file_import,
)
from app.features.integrations.services.supplier_data_normalization import (
    DEFAULT_CURRENCY,
    normalize_supplier_snapshot,
)
from app.features.integrations.services.supplier_sync_orchestrator import (
    adoption_locks,
)
from app.features.product.crud.product import crud_product
from app.features.product.models.product import Product, ProductUpdate
from app.features.product.services.overrides import strip_locked
from app.services.suppliers import is_api_supplier
from app.services.suppliers.base import NormalizedProductData

logger = logging.getLogger(__name__)

#: Seconds allowed to the supplier to answer for one reference.
ATTACH_TIMEOUT_SECONDS = 20.0


@dataclass(slots=True)
class AttachOutcome:
    #: ``adopted`` (done now) or ``pending`` (next file import).
    status: str
    message: str
    product: Product


def _not_linkable(product: Product, supplier_code: str | None, sku: str | None) -> None:
    if not supplier_code or not sku:
        raise AppError(
            code="supplier.attach.missing_reference",
            status_code=400,
            message="Choisissez le fournisseur et saisissez sa référence (SKU)",
            details={"product_id": str(product.id)},
        )
    if product.has_variants:
        raise AppError(
            code="supplier.attach.parent_product",
            status_code=400,
            message=(
                "Un article à déclinaisons ne se rattache pas : rattachez "
                "chacune de ses déclinaisons"
            ),
            details={"product_id": str(product.id)},
        )


async def _conflict(
    session: AsyncSession, product: Product, supplier_code: str, sku: str
) -> None:
    """Another product already holds this supplier reference: refuse to guess."""
    others = (
        await session.exec(
            select(Product).where(
                col(Product.supplier_name) == supplier_code,
                col(Product.supplier_sku) == sku,
                col(Product.id) != product.id,
            )
        )
    ).all()
    if others:
        raise AppError(
            code="supplier.attach.conflict",
            status_code=409,
            message=(
                f"La référence {sku} de {supplier_code} est déjà portée par "
                f"« {others[0].name} »"
            ),
            details={
                "supplier_name": supplier_code,
                "supplier_sku": sku,
                "product_ids": [str(p.id) for p in others],
            },
        )


async def attach_now(
    session: AsyncSession,
    product: Product,
    supplier: Supplier,
    *,
    supplier_sku: str,
) -> AttachOutcome:
    """Link ``product`` to ``supplier`` under ``supplier_sku`` and adopt it.

    Raises :class:`AppError` when the reference is taken by another product,
    unknown to the supplier (404) or when the supplier cannot be reached (502).
    """
    import asyncio

    supplier_code = supplier.code
    sku = supplier_sku.strip()
    _not_linkable(product, supplier_code, sku)
    await _conflict(session, product, supplier_code, sku)
    if not supplier.is_active:
        raise AppError(
            code="supplier.attach.inactive",
            status_code=400,
            message=f"Le fournisseur {supplier.name} est désactivé",
            details={"supplier_name": supplier_code},
        )

    if not is_api_supplier(supplier):
        # No API: record the link; the next import carrying it adopts it.
        await crud_product.update_draft(
            session=session,
            id=product.id,
            data=ProductUpdate(supplier_name=supplier_code, supplier_sku=sku),
            user=None,
            record=product,
        )
        return AttachOutcome(
            status="pending",
            message=(
                f"Rattaché à {supplier.name} : l'article sera adopté (coût et "
                f"stock) au prochain import de fichier contenant la référence {sku}."
            ),
            product=product,
        )

    orchestrator = orchestrator_for_file_import(supplier)
    adapter = orchestrator.adapter
    if not adapter.is_configured():
        raise AppError(
            code="supplier.attach.not_configured",
            status_code=400,
            message=f"Les identifiants de {supplier.name} ne sont pas configurés",
            details={"supplier_name": supplier_code},
        )
    try:
        pricing = await asyncio.wait_for(
            adapter.fetch_price_and_availability([sku]),
            timeout=ATTACH_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001 - reported to the admin as is
        raise AppError(
            code="supplier.attach.unreachable",
            status_code=502,
            message=f"{supplier.name} n'a pas répondu : {exc}",
            details={"supplier_name": supplier_code, "supplier_sku": sku},
        ) from exc
    found = pricing.get(sku)
    if found is None:
        raise AppError(
            code="supplier.attach.unknown_sku",
            status_code=404,
            message=f"{supplier.name} ne connaît pas la référence {sku}",
            details={"supplier_name": supplier_code, "supplier_sku": sku},
        )

    currency = found.currency or adapter.price_currency or DEFAULT_CURRENCY
    data: dict[str, Any] = {
        "supplier_name": supplier_code,
        "supplier_sku": sku,
        "is_supplier_managed": True,
        # Adoption makes the product supplier-managed, which would otherwise
        # hide it until Icecat knows it: it stays on sale as the admin wrote it.
        "published_without_enrichment": True,
        "last_supplier_sync": datetime.now(UTC),
        "supplier_missing_since": None,
    }
    if found.price is not None or found.quantity is not None:
        snapshot = normalize_supplier_snapshot(
            raw_price=found.price if found.price is not None else 0,
            raw_quantity=found.quantity if found.quantity is not None else 0,
            raw_currency=currency,
        )
        if found.quantity is not None:
            data["supplier_quantity"] = snapshot.supplier_quantity
        if found.price is not None:
            data["supplier_price"] = snapshot.supplier_price
            data["supplier_price_currency"] = snapshot.supplier_price_currency
            data["cost_amount"] = snapshot.supplier_price
            data["cost_currency"] = snapshot.supplier_price_currency
    if found.vendor_part_number and not product.vendor_part_number:
        data["vendor_part_number"] = found.vendor_part_number
    if found.manufacturer and not product.manufacturer:
        data["manufacturer"] = found.manufacturer
    if product.supplier_place_id is None and supplier.origin_place_id is not None:
        data["supplier_place_id"] = supplier.origin_place_id

    locks = adoption_locks(product)
    data = strip_locked(data, locks)
    data["overridden_fields"] = locks

    updated = await crud_product.update_draft(
        session=session,
        id=product.id,
        data=ProductUpdate(**data),
        user=None,
        record=product,
    )
    await orchestrator._upsert_mapping(
        session,
        updated,
        NormalizedProductData(
            supplier_sku=sku,
            name=updated.name,
            manufacturer=updated.manufacturer,
            vendor_part_number=updated.vendor_part_number,
        ),
    )
    quantity = data.get("supplier_quantity")
    logger.info(
        "Product %s attached to %s under %s (stock %s)",
        product.id,
        supplier_code,
        sku,
        quantity,
    )
    return AttachOutcome(
        status="adopted",
        message=(
            f"Rattaché à {supplier.name} : coût et stock repris"
            + (
                f" ({Decimal(str(quantity)).normalize():f} en stock)"
                if quantity is not None
                else ""
            )
            + ". Les champs saisis à la main restent verrouillés."
        ),
        product=updated,
    )


async def detach(session: AsyncSession, product: Product) -> Product:
    """Make ``product`` a manual product again.

    The supplier link and mapping go (no sync touches it any more), the
    supplier stock is zeroed (it would no longer be refreshed), the admin's
    locks stay. The next import carrying the old reference creates a new
    product, unless the reference is left out of the supplier's allowlist.
    """
    supplier_code = product.supplier_name
    if not supplier_code:
        raise AppError(
            code="supplier.detach.not_linked",
            status_code=400,
            message="Cet article n'est rattaché à aucun fournisseur",
            details={"product_id": str(product.id)},
        )
    product_id = product.id
    await session.exec(
        delete(SupplierProductMapping).where(
            col(SupplierProductMapping.supplier_name) == supplier_code,
            col(SupplierProductMapping.local_product_id) == product_id,
        )
    )
    updated = await crud_product.update_draft(
        session=session,
        id=product_id,
        data=ProductUpdate(
            is_supplier_managed=False,
            supplier_name=None,
            supplier_quantity=Decimal("0"),
            supplier_missing_since=None,
        ),
        user=None,
        record=product,
    )
    logger.info("Product %s detached from %s", product_id, supplier_code)
    return updated


__all__ = ["AttachOutcome", "attach_now", "detach"]
