"""Admin endpoints: create manual products and edit products with sync-safe overrides.

Editing a product here records every edited field in ``Product.overridden_fields``
so a later supplier sync or Icecat enrichment will not overwrite the admin's
values (rule in ``product/services/overrides.py``). Manual products
(``is_supplier_managed=False``) are never synced, so their overrides are moot but
recorded uniformly. A lock can be released field by field: the supplier value
then comes back with the next sync/enrichment, it is not restored on the spot.

A manual product may be linked to a declared supplier (``supplier_name`` =
``Supplier.code``): the supplier's origin warehouse and customs regime then
fill ``supplier_place_id`` and ``pricing_mode`` unless the payload sets them.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter

from app.api.deps import CurrentSuperUser, SessionDep
from app.core.errors import AppError
from app.features.base.crud import RecordNotFoundError
from app.features.integrations.models.supplier import Supplier
from app.features.product.crud.product import crud_product
from app.features.product.models.product import (
    PricingMode,
    ProductCreate,
    ProductPublic,
    ProductUpdate,
)
from app.features.product.services.overrides import merge_locks, release_lock
from app.services.suppliers import load_supplier

router = APIRouter(prefix="/admin/products", tags=["admin-product"])


async def _resolve_supplier(session: SessionDep, code: str | None) -> Supplier | None:
    """Load the supplier a payload points at (404 when the code is unknown)."""
    if not code:
        return None
    supplier = await load_supplier(session, code, include_inactive=True)
    if supplier is None:
        raise AppError(
            code="supplier.not_found",
            status_code=404,
            message=f"Unknown supplier '{code}'",
            details={"supplier_name": code},
        )
    return supplier


def _apply_supplier_defaults(data: dict[str, Any], supplier: Supplier | None) -> None:
    """Fill origin and pricing mode from the supplier when the payload is silent."""
    if supplier is None:
        return
    if "supplier_place_id" not in data and supplier.origin_place_id is not None:
        data["supplier_place_id"] = supplier.origin_place_id
    if "pricing_mode" not in data:
        data["pricing_mode"] = (
            PricingMode.DOMESTIC if supplier.is_domestic else PricingMode.IMPORT
        )


@router.post("", response_model=ProductPublic)
async def admin_create_product(
    session: SessionDep,
    current_user: CurrentSuperUser,
    payload: ProductCreate,
) -> ProductPublic:
    """Create a manually-managed product (never overwritten by the supplier sync)."""
    data = payload.model_dump(exclude_unset=True)
    supplier = await _resolve_supplier(session, data.get("supplier_name"))
    _apply_supplier_defaults(data, supplier)
    create_data = ProductCreate.model_validate({**data, "is_supplier_managed": False})
    product = await crud_product.create(
        session=session, data=create_data, user=current_user
    )
    return ProductPublic.model_validate(product)


@router.put("/{product_id}", response_model=ProductPublic)
async def admin_update_product(
    session: SessionDep,
    current_user: CurrentSuperUser,
    product_id: uuid.UUID,
    payload: ProductUpdate,
) -> ProductPublic:
    """Update a product and lock the edited fields against the supplier sync.

    Every content field present in the payload is added to ``overridden_fields``.
    """
    try:
        product = await crud_product.read(session=session, id=product_id)
    except RecordNotFoundError as exc:
        raise AppError(
            code="product.not_found",
            status_code=404,
            message=f"Product '{product_id}' not found",
            details={"product_id": str(product_id)},
        ) from exc

    changed = payload.model_dump(exclude_unset=True)
    if "supplier_name" in changed and changed["supplier_name"] != product.supplier_name:
        supplier = await _resolve_supplier(session, changed["supplier_name"])
        # Re-linking a manual product to another supplier moves its origin
        # and customs regime along, unless the same payload sets them.
        if not product.is_supplier_managed:
            _apply_supplier_defaults(changed, supplier)
    merged = merge_locks(product.overridden_fields, changed)

    update_data: dict[str, Any] = {**changed, "overridden_fields": merged}
    updated = await crud_product.update(
        session=session,
        id=product_id,
        data=update_data,
        user=current_user,
        record=product,
    )
    return ProductPublic.model_validate(updated)


@router.delete("/{product_id}/overrides/{field}", response_model=ProductPublic)
async def admin_release_override(
    session: SessionDep,
    current_user: CurrentSuperUser,
    product_id: uuid.UUID,
    field: str,
) -> ProductPublic:
    """Release one field lock so the supplier/enrichment value can come back.

    The current (admin) value stays until the next sync or enrichment rewrites
    it — no supplier copy is kept alongside.
    """
    try:
        product = await crud_product.read(session=session, id=product_id)
    except RecordNotFoundError as exc:
        raise AppError(
            code="product.not_found",
            status_code=404,
            message=f"Product '{product_id}' not found",
            details={"product_id": str(product_id)},
        ) from exc

    if field not in (product.overridden_fields or []):
        raise AppError(
            code="product.override.not_locked",
            status_code=404,
            message=f"Field '{field}' is not locked on this product",
            details={"product_id": str(product_id), "field": field},
        )

    updated = await crud_product.update(
        session=session,
        id=product_id,
        data={"overridden_fields": release_lock(product.overridden_fields, field)},
        user=current_user,
        record=product,
    )
    return ProductPublic.model_validate(updated)
