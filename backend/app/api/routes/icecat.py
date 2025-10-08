"""
API routes for Icecat product enrichment management.
Provides endpoints for manual enrichment and monitoring.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import SessionDep, get_current_active_superuser
from app.core.config import settings
from app.services.icecat_service import icecat_service
from app.tasks.icecat_tasks import trigger_batch_enrichment, trigger_product_enrichment

router = APIRouter()


class EnrichmentRequest(BaseModel):
    """Request model for product enrichment"""

    product_id: str = Field(description="Product ID to enrich with Icecat data")


class BatchEnrichmentRequest(BaseModel):
    """Request model for batch enrichment"""

    limit: int = Field(
        default=50, description="Maximum number of products to process", ge=1, le=500
    )


class EnrichmentResponse(BaseModel):
    """Response model for enrichment operations"""

    job_id: str = Field(description="ARQ job ID for tracking")
    status: str = Field(description="Operation status")
    message: str = Field(description="Human-readable message")
    timestamp: datetime = Field(description="Operation timestamp")


class TestEnrichmentRequest(BaseModel):
    """Request model for testing enrichment"""

    vendor_part_number: str | None = Field(default=None, description="Manufacturer part number")
    manufacturer: str | None = Field(default=None, description="Product manufacturer/brand")
    ean: str | None = Field(default=None, description="Optional EAN/UPC code")
    upc: str | None = Field(default=None, description="Optional UPC code")


@router.post("/enrich", response_model=EnrichmentResponse)
async def enrich_product(
    request: EnrichmentRequest,
    session: SessionDep,
    current_user=Depends(get_current_active_superuser),
) -> EnrichmentResponse:
    """
    Manually trigger Icecat enrichment for a specific product.

    This will queue a background job to fetch product data from Icecat
    and update the product with images, specifications, and features.

    **Required permissions:** Superuser only
    """
    if not settings.ICECAT_ENABLED:
        raise HTTPException(
            status_code=400, detail="Icecat enrichment is disabled in settings"
        )

    try:
        job_id = await trigger_product_enrichment(request.product_id)

        return EnrichmentResponse(
            job_id=job_id,
            status="queued",
            message=f"Icecat enrichment job queued for product {request.product_id}",
            timestamp=datetime.utcnow(),
        )

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to queue enrichment job: {str(e)}"
        )


@router.post("/enrich/batch", response_model=EnrichmentResponse)
async def batch_enrich_products(
    request: BatchEnrichmentRequest,
    session: SessionDep,
    current_user=Depends(get_current_active_superuser),
) -> EnrichmentResponse:
    """
    Manually trigger batch Icecat enrichment for multiple products.

    This will queue a background job to enrich up to `limit` products
    that are supplier-managed and not yet enriched with Icecat data.

    **Required permissions:** Superuser only
    """
    if not settings.ICECAT_ENABLED:
        raise HTTPException(
            status_code=400, detail="Icecat enrichment is disabled in settings"
        )

    try:
        job_id = await trigger_batch_enrichment(request.limit)

        return EnrichmentResponse(
            job_id=job_id,
            status="queued",
            message=f"Batch Icecat enrichment job queued for up to {request.limit} products",
            timestamp=datetime.utcnow(),
        )

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to queue batch enrichment job: {str(e)}"
        )


@router.post("/test", response_model=dict[str, Any])
async def test_icecat_enrichment(
    request: TestEnrichmentRequest,
#    current_user=Depends(get_current_active_superuser),
) -> dict[str, Any]:
    """
    Test Icecat API connection and data retrieval.

    This endpoint is useful for testing credentials and verifying
    that product data can be retrieved from Icecat.

    **Required permissions:** Superuser only
    """
    if not settings.ICECAT_ENABLED:
        raise HTTPException(
            status_code=400, detail="Icecat enrichment is disabled in settings"
        )

    try:
        enrichment_data = await icecat_service.enrich_product_with_icecat(
            vendor_part_number=request.vendor_part_number,
            manufacturer=request.manufacturer,
            ean=request.ean,
            upc=request.upc,
        )

        if not enrichment_data:
            return {
                "status": "not_found",
                "message": "No Icecat data found for the specified product",
                "vendor_part_number": request.vendor_part_number,
                "manufacturer": request.manufacturer,
            }

        return {
            "status": "success",
            "message": "Icecat data retrieved successfully",
            "data": enrichment_data,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Icecat API test failed: {str(e)}",
        )


@router.get("/status")
async def get_enrichment_status(
    current_user=Depends(get_current_active_superuser),
) -> dict[str, Any]:
    """
    Get Icecat enrichment status and configuration.

    Returns information about Icecat integration status,
    configuration, and statistics.

    **Required permissions:** Superuser only
    """
    return {
        "enabled": settings.ICECAT_ENABLED,
        "configured": bool(settings.ICECAT_USERNAME and settings.ICECAT_API_KEY),
        "language": settings.ICECAT_LANGUAGE,
        "api_url": icecat_service.base_url,
    }


@router.get("/search/upc/{upc}", response_model=dict[str, Any])
async def search_by_upc(
    upc: str,
#    current_user=Depends(get_current_active_superuser),
) -> dict[str, Any]:
    """
    Search Icecat product by UPC code.

    UPC-A codes (12 digits) are automatically converted to EAN-13.
    This endpoint is useful for testing and debugging UPC-based searches.

    **Required permissions:** Superuser only
    """
    if not settings.ICECAT_ENABLED:
        raise HTTPException(
            status_code=400, detail="Icecat enrichment is disabled in settings"
        )

    try:
        product_data = await icecat_service.get_product_by_upc(upc)
        
        if not product_data:
            return {
                "status": "not_found",
                "message": f"No product found for UPC: {upc}",
                "upc": upc,
            }

        return {
            "status": "success",
            "message": "Product found",
            "upc": upc,
            "data": {
                "ean": product_data.ean,
                "brand": product_data.brand,
                "product_name": product_data.product_name,
                "description": product_data.description,
                "category": product_data.category,
                "manufacturer_code": product_data.manufacturer_code,
                "images_count": len(product_data.images),
                "specifications_count": len(product_data.specifications),
                "features_count": len(product_data.features),
            },
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"UPC search failed: {str(e)}",
        )


@router.get("/search/ean/{ean}", response_model=dict[str, Any])
async def search_by_ean(
    ean: str,
#    current_user=Depends(get_current_active_superuser),
) -> dict[str, Any]:
    """
    Search Icecat product by EAN code.

    This endpoint is useful for testing and debugging EAN-based searches.

    **Required permissions:** Superuser only
    """
    if not settings.ICECAT_ENABLED:
        raise HTTPException(
            status_code=400, detail="Icecat enrichment is disabled in settings"
        )

    try:
        product_data = await icecat_service.get_product_by_ean(ean)
        
        if not product_data:
            return {
                "status": "not_found",
                "message": f"No product found for EAN: {ean}",
                "ean": ean,
            }

        return {
            "status": "success",
            "message": "Product found",
            "ean": ean,
            "data": {
                "ean": product_data.ean,
                "brand": product_data.brand,
                "product_name": product_data.product_name,
                "description": product_data.description,
                "category": product_data.category,
                "manufacturer_code": product_data.manufacturer_code,
                "images_count": len(product_data.images),
                "specifications_count": len(product_data.specifications),
                "features_count": len(product_data.features),
            },
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"EAN search failed: {str(e)}",
        )

