"""Admin endpoints: create manual products and edit products with sync-safe overrides.

Editing a product here records every edited field in ``Product.overridden_fields``
so a later supplier sync will not overwrite the admin's values (see
``SupplierSyncOrchestrator.upsert_product``). Manual products
(``is_supplier_managed=False``) are never synced, so their overrides are moot but
recorded uniformly.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter

from app.api.deps import CurrentSuperUser, SessionDep
from app.core.errors import AppError
from app.features.base.crud import RecordNotFoundError
from app.features.product.crud.product import crud_product
from app.features.product.models.product import (
    ProductCreate,
    ProductPublic,
    ProductUpdate,
)

router = APIRouter(prefix="/admin/products", tags=["admin-product"])

# Flags / bookkeeping that must never be recorded as content overrides.
_NON_OVERRIDE_FIELDS = {"is_active", "is_admin_active", "overridden_fields"}


@router.post("", response_model=ProductPublic)
async def admin_create_product(
    session: SessionDep,
    current_user: CurrentSuperUser,
    payload: ProductCreate,
) -> ProductPublic:
    """Create a manually-managed product (never overwritten by the supplier sync)."""
    create_data = ProductCreate.model_validate(
        {**payload.model_dump(exclude_unset=True), "is_supplier_managed": False}
    )
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
    edited = [key for key in changed if key not in _NON_OVERRIDE_FIELDS]
    merged = sorted(set(product.overridden_fields or []) | set(edited))

    update_data: dict[str, Any] = {**changed, "overridden_fields": merged}
    updated = await crud_product.update(
        session=session,
        id=product_id,
        data=update_data,
        user=current_user,
        record=product,
    )
    return ProductPublic.model_validate(updated)
