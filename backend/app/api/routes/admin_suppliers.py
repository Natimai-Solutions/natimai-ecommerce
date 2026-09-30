"""Admin back-office of the ``suppliers`` table.

  GET    /admin/suppliers            — every supplier (inactive included)
  GET    /admin/suppliers/adapters   — implementations available in the code
  POST   /admin/suppliers            — declare a supplier
  GET    /admin/suppliers/{code}
  PATCH  /admin/suppliers/{code}     — partial update (``code`` is immutable)
  DELETE /admin/suppliers/{code}     — deactivate (products keep their link)
  GET    /admin/suppliers/{code}/sku-allowlist — the references we follow
  PUT    /admin/suppliers/{code}/sku-allowlist — replace that list

A supplier of kind ``api`` must name a registered ``adapter_key``; a ``file``
supplier's ``column_mapping`` must at least map the two required fields.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, func, select

from app.api.deps import CurrentSuperUser, SessionDep
from app.core.errors import AppError
from app.features.integrations.models.supplier import (
    AdapterDescriptor,
    Supplier,
    SupplierCreate,
    SupplierKind,
    SupplierPublic,
    SuppliersPublic,
    SupplierUpdate,
)
from app.features.integrations.services.sku_allowlist import (
    AllowlistView,
    AllowlistWrite,
    allowlist_view,
    save_allowlist,
)
from app.features.place.models import Place
from app.features.product.models.product import Product
from app.services.suppliers import (
    ADAPTERS,
    adapter_for_supplier,
    describe_adapters,
    forget_adapter,
    has_adapter,
)
from app.services.suppliers.file_import import validate_mapping

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/suppliers", tags=["admin-suppliers"])


def _public(supplier: Supplier) -> SupplierPublic:
    configured = True
    if supplier.kind == SupplierKind.API:
        configured = (
            has_adapter(supplier.adapter_key)
            and ADAPTERS[str(supplier.adapter_key)].credentials_present()
        )
    public = SupplierPublic.model_validate(supplier)
    public.configured = configured
    return public


async def _load(session: SessionDep, code: str) -> Supplier:
    result = await session.exec(select(Supplier).where(Supplier.code == code))
    supplier = result.first()
    if supplier is None:
        raise AppError(
            code="supplier.not_found",
            status_code=404,
            message=f"Unknown supplier '{code}'",
            details={"supplier_name": code},
        )
    return supplier


async def _validate(session: SessionDep, supplier: Supplier) -> None:
    """Cross-field checks shared by create and update."""
    if supplier.kind == SupplierKind.API:
        if not has_adapter(supplier.adapter_key):
            raise AppError(
                code="supplier.adapter.unknown",
                status_code=400,
                message=(
                    f"No integration registered under adapter_key "
                    f"{supplier.adapter_key!r}. Available: {', '.join(sorted(ADAPTERS))}"
                ),
                details={
                    "adapter_key": supplier.adapter_key,
                    "available": sorted(ADAPTERS),
                },
            )
        allowed = set(ADAPTERS[str(supplier.adapter_key)].settings_keys)
        unknown = sorted(set(supplier.settings or {}) - allowed)
        if unknown:
            raise AppError(
                code="supplier.settings.unknown_keys",
                status_code=400,
                message=f"Unknown settings for {supplier.adapter_key}: {', '.join(unknown)}",
                details={"unknown": unknown, "allowed": sorted(allowed)},
            )
    if supplier.kind == SupplierKind.FILE and supplier.column_mapping:
        problems = validate_mapping(supplier.column_mapping)
        if problems:
            raise AppError(
                code="supplier.import.mapping_invalid",
                status_code=400,
                message="; ".join(problems),
                details={"problems": problems},
            )
    if supplier.origin_place_id is not None:
        place = await session.get(Place, supplier.origin_place_id)
        if place is None:
            raise AppError(
                code="supplier.origin_place.not_found",
                status_code=400,
                message=f"Place '{supplier.origin_place_id}' does not exist",
                details={"origin_place_id": str(supplier.origin_place_id)},
            )


@router.get("", response_model=SuppliersPublic)
async def list_suppliers(
    session: SessionDep, _current_user: CurrentSuperUser
) -> SuppliersPublic:
    """Every declared supplier, active or not."""
    result = await session.exec(select(Supplier).order_by(col(Supplier.name).asc()))
    rows = list(result.all())
    return SuppliersPublic(data=[_public(s) for s in rows], count=len(rows))


@router.get("/adapters", response_model=list[AdapterDescriptor])
async def list_adapters(_current_user: CurrentSuperUser) -> list[AdapterDescriptor]:
    """Integrations available in the code, for the ``adapter_key`` dropdown."""
    return describe_adapters()


@router.post("", response_model=SupplierPublic, status_code=201)
async def create_supplier(
    payload: SupplierCreate,
    session: SessionDep,
    current_user: CurrentSuperUser,
) -> SupplierPublic:
    """Declare a supplier."""
    # Read before any commit: the session expires ORM instances on commit and
    # a lazy reload of ``current_user`` would then fail in async mode.
    actor_id = current_user.id
    supplier = Supplier.model_validate(payload)
    await _validate(session, supplier)
    session.add(supplier)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AppError(
            code="supplier.code.conflict",
            status_code=409,
            message=f"A supplier with code '{payload.code}' already exists",
            details={"code": payload.code},
        ) from exc
    await session.refresh(supplier)
    logger.info("Admin %s created supplier %s", actor_id, supplier.code)
    return _public(supplier)


@router.get("/{code}", response_model=SupplierPublic)
async def get_supplier(
    code: str, session: SessionDep, _current_user: CurrentSuperUser
) -> SupplierPublic:
    """One supplier by code."""
    return _public(await _load(session, code))


@router.patch("/{code}", response_model=SupplierPublic)
async def update_supplier(
    code: str,
    payload: SupplierUpdate,
    session: SessionDep,
    current_user: CurrentSuperUser,
) -> SupplierPublic:
    """Partial update; the adapter instance is rebuilt on the next use."""
    actor_id = current_user.id
    supplier = await _load(session, code)
    fields = payload.model_dump(exclude_unset=True)
    for name, value in fields.items():
        setattr(supplier, name, value)
    supplier.updated_at = datetime.now(timezone.utc)
    await _validate(session, supplier)
    session.add(supplier)
    await session.commit()
    await session.refresh(supplier)
    forget_adapter(supplier.code)
    logger.info("Admin %s updated supplier %s: %s", actor_id, code, sorted(fields))
    return _public(supplier)


@router.get("/{code}/sku-allowlist", response_model=AllowlistView)
async def get_sku_allowlist(
    code: str, session: SessionDep, _current_user: CurrentSuperUser
) -> AllowlistView:
    """The references the shop follows at this supplier, against its catalogue."""
    return await allowlist_view(session, await _load(session, code))


@router.put("/{code}/sku-allowlist", response_model=AllowlistView)
async def put_sku_allowlist(
    code: str,
    payload: AllowlistWrite,
    session: SessionDep,
    current_user: CurrentSuperUser,
) -> AllowlistView:
    """Replace the list (empty clears it: the whole catalogue is followed).

    Managed products outside a non-empty list leave the storefront now; the
    listed ones are created or refreshed by the next syncs.
    """
    actor_id = current_user.id
    supplier = await _load(session, code)
    view = await save_allowlist(session, supplier, payload.skus)
    await session.commit()
    forget_adapter(code)
    logger.info(
        "Admin %s set the SKU allowlist of %s: %d references, %d products hidden",
        actor_id,
        code,
        len(view.entries),
        view.deactivated,
    )
    return view


@router.delete("/{code}", response_model=SupplierPublic)
async def deactivate_supplier(
    code: str, session: SessionDep, current_user: CurrentSuperUser
) -> SupplierPublic:
    """Deactivate a supplier (its products keep their ``supplier_name``).

    Nothing is deleted: the code stays reserved so the links from products,
    mappings, sync logs and supplier orders keep resolving.
    """
    actor_id = current_user.id
    supplier = await _load(session, code)
    count_result = await session.exec(
        select(func.count(col(Product.id))).where(Product.supplier_name == code)
    )
    linked = int(count_result.one())
    supplier.is_active = False
    supplier.sync_enabled = False
    supplier.updated_at = datetime.now(timezone.utc)
    session.add(supplier)
    await session.commit()
    await session.refresh(supplier)
    forget_adapter(code)
    logger.warning(
        "Admin %s deactivated supplier %s (%d linked products)",
        actor_id,
        code,
        linked,
    )
    return _public(supplier)


__all__ = ["router", "adapter_for_supplier"]
