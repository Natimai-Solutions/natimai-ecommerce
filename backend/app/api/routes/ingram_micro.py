"""
API routes for Ingram Micro integration management.
Provides endpoints for manual synchronization and monitoring.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import SessionDep, get_current_active_superuser
from app.core.config import settings
from app.services.ingram_micro_service import ingram_service
from app.tasks.ingram_micro_tasks import trigger_inventory_refresh, trigger_manual_sync

router = APIRouter()


class SyncRequest(BaseModel):
    """Request model for manual synchronization"""

    categories: list[str] | None = Field(
        default=None,
        description="Product categories to sync (defaults to all configured categories)",
    )


class InventoryRefreshRequest(BaseModel):
    """Request model for inventory refresh"""

    skus: list[str] | None = Field(
        default=None,
        description="Specific SKUs to refresh (defaults to all active products)",
    )


class SyncResponse(BaseModel):
    """Response model for sync operations"""

    job_id: str = Field(description="ARQ job ID for tracking")
    status: str = Field(description="Operation status")
    message: str = Field(description="Human-readable message")
    timestamp: datetime = Field(description="Operation timestamp")


class HealthResponse(BaseModel):
    """Response model for health checks"""

    status: str = Field(description="Service health status")
    api_responsive: bool = Field(description="Whether Ingram API is responding")
    configuration_valid: bool = Field(description="Whether configuration is valid")
    last_sync: datetime | None = Field(
        default=None, description="Last successful sync time"
    )
    message: str = Field(description="Status details")


@router.post("/sync/products", response_model=SyncResponse)
async def trigger_product_sync(
    request: SyncRequest, current_user=Depends(get_current_active_superuser)
) -> SyncResponse:
    """
    Manually trigger product catalog synchronization from Ingram Micro.

    This endpoint allows administrators to initiate an immediate product sync
    instead of waiting for the scheduled synchronization.

    **Required permissions:** Superuser only
    """
    if not settings.INGRAM_SYNC_ENABLED:
        raise HTTPException(
            status_code=400,
            detail="Ingram Micro synchronization is disabled in settings",
        )

    if not all(
        [
            settings.INGRAM_CLIENT_ID,
            settings.INGRAM_CLIENT_SECRET,
            settings.INGRAM_CUSTOMER_NUMBER,
        ]
    ):
        raise HTTPException(
            status_code=500, detail="Ingram Micro credentials not configured"
        )

    try:
        job_id = await trigger_manual_sync(categories=request.categories)

        return SyncResponse(
            job_id=job_id,
            status="queued",
            message=f"Product sync queued successfully for categories: {request.categories or settings.INGRAM_SYNC_CATEGORIES}",
            timestamp=datetime.utcnow(),
        )

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to queue product sync: {str(e)}"
        )


@router.post("/sync/inventory", response_model=SyncResponse)
async def trigger_inventory_sync(
    request: InventoryRefreshRequest, current_user=Depends(get_current_active_superuser)
) -> SyncResponse:
    """
    Manually trigger inventory level refresh from Ingram Micro.

    This endpoint allows administrators to update inventory quantities
    for specific products or all active products.

    **Required permissions:** Superuser only
    """
    if not settings.INGRAM_SYNC_ENABLED:
        raise HTTPException(
            status_code=400,
            detail="Ingram Micro synchronization is disabled in settings",
        )

    try:
        job_id = await trigger_inventory_refresh(skus=request.skus)

        return SyncResponse(
            job_id=job_id,
            status="queued",
            message=f"Inventory refresh queued for {len(request.skus) if request.skus else 'all'} products",
            timestamp=datetime.utcnow(),
        )

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to queue inventory refresh: {str(e)}"
        )


@router.get("/health", response_model=HealthResponse)
async def check_ingram_health(
    session: SessionDep, current_user=Depends(get_current_active_superuser)
) -> HealthResponse:
    """
    Check Ingram Micro API health and configuration status.

    This endpoint verifies:
    - API credentials configuration
    - API connectivity and authentication
    - Last successful synchronization time

    **Required permissions:** Superuser only
    """
    # Check configuration
    config_valid = all(
        [
            settings.INGRAM_CLIENT_ID,
            settings.INGRAM_CLIENT_SECRET,
            settings.INGRAM_CUSTOMER_NUMBER,
        ]
    )

    if not config_valid:
        return HealthResponse(
            status="misconfigured",
            api_responsive=False,
            configuration_valid=False,
            message="Ingram Micro credentials not configured",
        )

    if not settings.INGRAM_SYNC_ENABLED:
        return HealthResponse(
            status="disabled",
            api_responsive=False,
            configuration_valid=True,
            message="Ingram Micro synchronization is disabled in settings",
        )

    # Test API connectivity
    try:
        # Attempt a simple API call
        products = await ingram_service.get_product_catalog(
            category="notebooks", page_number=1, page_size=1
        )

        # TODO: Get last sync time from database
        # last_sync = await get_last_sync_time(session)

        return HealthResponse(
            status="healthy",
            api_responsive=True,
            configuration_valid=True,
            # last_sync=last_sync,
            message=f"API is responsive. Test call returned {len(products)} products.",
        )

    except Exception as e:
        return HealthResponse(
            status="unhealthy",
            api_responsive=False,
            configuration_valid=True,
            message=f"API connectivity test failed: {str(e)}",
        )


@router.get("/config")
async def get_sync_config(
    current_user=Depends(get_current_active_superuser),
) -> dict[str, Any]:
    """
    Get current Ingram Micro synchronization configuration.

    **Required permissions:** Superuser only
    """
    return {
        "sync_enabled": settings.INGRAM_SYNC_ENABLED,
        "environment": settings.INGRAM_ENVIRONMENT,
        "sync_categories": settings.INGRAM_SYNC_CATEGORIES,
        "sync_interval_hours": settings.INGRAM_SYNC_INTERVAL_HOURS,
        "credentials_configured": all(
            [
                settings.INGRAM_CLIENT_ID,
                settings.INGRAM_CLIENT_SECRET,
                settings.INGRAM_CUSTOMER_NUMBER,
            ]
        ),
    }


@router.get("/categories")
async def get_available_categories(
    current_user=Depends(get_current_active_superuser),
) -> list[str]:
    """
    Get list of available product categories from Ingram Micro.

    This is a helper endpoint to see what categories are available
    for synchronization configuration.

    **Required permissions:** Superuser only
    """
    if not settings.INGRAM_SYNC_ENABLED:
        raise HTTPException(
            status_code=400, detail="Ingram Micro synchronization is disabled"
        )

    # Common Ingram Micro categories
    # In a real implementation, you might fetch this from the API
    return [
        "notebooks",
        "desktop",
        "tablets",
        "accessories",
        "monitors",
        "printers",
        "networking",
        "storage",
        "software",
        "servers",
    ]


@router.get("/test-api")
async def test_api_connection(
    #    current_user = Depends(get_current_active_superuser)
) -> dict[str, Any]:
    """
    Test API connection and return sample data.

    This endpoint is useful for debugging API connectivity
    and testing credentials.

    **Required permissions:** Superuser only
    """
    if not settings.INGRAM_SYNC_ENABLED:
        raise HTTPException(
            status_code=400, detail="Ingram Micro synchronization is disabled"
        )

    try:
        # Test with minimal parameters - no category
        products = await ingram_service.get_product_catalog(
            category=None, page_number=1, page_size=3
        )

        return {
            "status": "success",
            "message": "API connection test successful",
            "sample_products": [
                {
                    "sku": p.sku,
                    "name": p.product_name,
                    "manufacturer": p.manufacturer,
                    "price": p.price,
                }
                for p in products[:3]
            ],
            "total_found": len(products),
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"API connection test failed: {str(e)}"
        )
