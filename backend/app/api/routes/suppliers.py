"""
Generic supplier integration routes.

One router serves every registered distributor; the ``{supplier_name}`` path
parameter selects the adapter. Add a supplier by registering its adapter in
:mod:`app.services.suppliers` — no new routes needed.
"""

import logging
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, Field

from app.api.deps import CurrentSuperUser, SessionDep
from app.core.errors import AppError
from app.features.integrations.crud.supplier_sync import supplier_sync_log_crud
from app.features.integrations.models.supplier_sync import SyncType
from app.services.suppliers import (
    SupplierAdapter,
    get_adapter,
    has_supplier,
    supplier_names,
)
from app.tasks.supplier_tasks import (
    backfill_product_categories_task,
    trigger_inventory_refresh,
    trigger_manual_sync,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


def get_supplier_adapter(
    supplier_name: Annotated[str, Path(description="Registered supplier machine name")],
) -> SupplierAdapter:
    """Get supplier adapter."""
    if not has_supplier(supplier_name):
        registered_suppliers = list(supplier_names())
        raise AppError(
            code="supplier.not_found",
            status_code=404,
            message=f"Unknown supplier '{supplier_name}'. "
            f"Registered: {', '.join(registered_suppliers)}",
            details={
                "supplier_name": supplier_name,
                "registered": registered_suppliers,
            },
        )
    return get_adapter(supplier_name)


AdapterDep = Annotated[SupplierAdapter, Depends(get_supplier_adapter)]


# -- schemas --------------------------------------------------------------


class SupplierSummary(BaseModel):
    """Represents supplier summary."""

    name: str
    display_name: str
    configured: bool
    sync_enabled: bool
    default_categories: list[str] = Field(default_factory=list)


class SyncRequest(BaseModel):
    """Represents sync request."""

    categories: list[str] | None = Field(
        default=None,
        description="Categories to sync (defaults to the supplier's configured list)",
    )


class InventoryRefreshRequest(BaseModel):
    """Represents inventory refresh request."""

    skus: list[str] | None = Field(
        default=None,
        description="Specific SKUs to refresh (defaults to all stale products)",
    )


class SyncResponse(BaseModel):
    """Represents sync response."""

    job_id: str
    supplier_name: str
    status: str
    message: str
    timestamp: datetime


class HealthResponse(BaseModel):
    """Represents health response."""

    supplier_name: str
    status: str
    api_responsive: bool
    configuration_valid: bool
    last_sync: datetime | None = None
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


# -- routes ---------------------------------------------------------------


@router.get("", response_model=list[SupplierSummary])
async def list_suppliers(_current_user: CurrentSuperUser) -> list[SupplierSummary]:
    """List all registered suppliers and their configuration status.

    **Required permissions:** Superuser only
    """
    summaries = []
    for name in supplier_names():
        adapter = get_adapter(name)
        summaries.append(
            SupplierSummary(
                name=adapter.name,
                display_name=adapter.display_name,
                configured=adapter.is_configured(),
                sync_enabled=adapter.is_sync_enabled(),
                default_categories=list(adapter.default_categories),
            )
        )
    return summaries


@router.post("/{supplier_name}/sync/products", response_model=SyncResponse)
async def trigger_product_sync(
    adapter: AdapterDep,
    request: SyncRequest,
    _current_user: CurrentSuperUser,
) -> SyncResponse:
    """Queue a catalog synchronization for the supplier.

    **Required permissions:** Superuser only
    """
    if not adapter.is_sync_enabled():
        raise AppError(
            code="supplier.sync.disabled",
            status_code=400,
            message=f"{adapter.display_name} synchronization is disabled in settings",
            details={"supplier_name": adapter.name},
        )
    if not adapter.is_configured():
        raise AppError(
            code="supplier.credentials.not_configured",
            status_code=500,
            message=f"{adapter.display_name} credentials not configured",
            details={"supplier_name": adapter.name},
        )

    categories = request.categories or list(adapter.default_categories)
    try:
        job_id = await trigger_manual_sync(adapter.name, categories=categories)
    except Exception as e:
        raise AppError(
            code="supplier.sync.queue_failed",
            status_code=500,
            message=f"Failed to queue product sync: {e}",
            details={
                "supplier_name": adapter.name,
                "sync_type": "product_catalog",
                "reason": str(e),
            },
        ) from e

    return SyncResponse(
        job_id=job_id,
        supplier_name=adapter.name,
        status="queued",
        message=f"Product sync queued for categories: {categories}",
        timestamp=datetime.now(timezone.utc),
    )


@router.post("/{supplier_name}/sync/inventory", response_model=SyncResponse)
async def trigger_inventory_sync(
    adapter: AdapterDep,
    request: InventoryRefreshRequest,
    _current_user: CurrentSuperUser,
) -> SyncResponse:
    """Queue a price & availability refresh for the supplier.

    **Required permissions:** Superuser only
    """
    if not adapter.is_sync_enabled():
        raise AppError(
            code="supplier.sync.disabled",
            status_code=400,
            message=f"{adapter.display_name} synchronization is disabled in settings",
            details={"supplier_name": adapter.name},
        )
    if not adapter.is_configured():
        raise AppError(
            code="supplier.credentials.not_configured",
            status_code=500,
            message=f"{adapter.display_name} credentials not configured",
            details={"supplier_name": adapter.name},
        )

    try:
        job_id = await trigger_inventory_refresh(adapter.name, skus=request.skus)
    except Exception as e:
        raise AppError(
            code="supplier.sync.queue_failed",
            status_code=500,
            message=f"Failed to queue inventory refresh: {e}",
            details={
                "supplier_name": adapter.name,
                "sync_type": "inventory",
                "reason": str(e),
            },
        ) from e

    count = len(request.skus) if request.skus else "all stale"
    return SyncResponse(
        job_id=job_id,
        supplier_name=adapter.name,
        status="queued",
        message=f"Inventory refresh queued for {count} products",
        timestamp=datetime.now(timezone.utc),
    )


@router.get("/{supplier_name}/health", response_model=HealthResponse)
async def check_supplier_health(
    adapter: AdapterDep,
    session: SessionDep,
    _current_user: CurrentSuperUser,
) -> HealthResponse:
    """Check the supplier API health, configuration and last successful sync.

    **Required permissions:** Superuser only
    """
    last_successful_sync = await supplier_sync_log_crud.get_last_successful_sync(
        session=session,
        supplier_name=adapter.name,
        sync_type=SyncType.PRODUCT_CATALOG,
    )
    last_sync = (
        (last_successful_sync.completed_at or last_successful_sync.started_at)
        if last_successful_sync
        else None
    )

    health = await adapter.health_check()
    if not health.configured:
        status = "misconfigured"
    elif not adapter.is_sync_enabled():
        status = "disabled"
    elif health.healthy:
        status = "healthy"
    else:
        status = "unhealthy"

    return HealthResponse(
        supplier_name=adapter.name,
        status=status,
        api_responsive=health.healthy,
        configuration_valid=health.configured,
        last_sync=last_sync,
        message=health.message,
        details=health.details,
    )


@router.get("/{supplier_name}/config")
async def get_supplier_config(
    adapter: AdapterDep,
    _current_user: CurrentSuperUser,
) -> dict[str, Any]:
    """Get the supplier's (credential-free) synchronization configuration.

    **Required permissions:** Superuser only
    """
    return adapter.config_summary()


@router.get("/{supplier_name}/categories", response_model=list[str])
async def get_supplier_categories(
    adapter: AdapterDep,
    _current_user: CurrentSuperUser,
) -> list[str]:
    """Get the supplier's configured default categories.

    **Required permissions:** Superuser only
    """
    return list(adapter.default_categories)


@router.post("/admin/backfill-product-categories")
async def trigger_category_backfill(
    _current_user: CurrentSuperUser,
    batch_size: int = 200,
) -> dict[str, Any]:
    """Trigger a one-shot backfill: populate Product.category_id from supplier_subcategory.

    Safe to re-run (idempotent). Runs inline (blocking) — use for maintenance windows.
    **Required permissions:** Superuser only
    """
    stats = await backfill_product_categories_task({}, batch_size=batch_size)
    return {"status": "completed", **stats}
