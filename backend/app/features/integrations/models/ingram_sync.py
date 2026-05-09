"""
Models for Ingram Micro synchronization history and logs.
Tracks sync operations, results, and audit trail.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel
from sqlmodel import JSON, Column, Field, SQLModel


class SyncStatus(str, Enum):
    """Synchronization status enum"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"


class SyncType(str, Enum):
    """Type of synchronization operation"""

    PRODUCT_CATALOG = "product_catalog"
    INVENTORY_UPDATE = "inventory_update"
    HEALTH_CHECK = "health_check"


class IngramSyncLogBase(SQLModel):
    """Base model for Ingram Micro sync logs"""

    sync_type: SyncType = Field(description="Type of synchronization operation")
    status: SyncStatus = Field(
        default=SyncStatus.PENDING, description="Synchronization status"
    )
    categories: list[str] | None = Field(
        default=None,
        sa_column=Column(JSON),
        description="Product categories included in sync",
    )
    skus: list[str] | None = Field(
        default=None,
        sa_column=Column(JSON),
        description="Specific SKUs processed (for inventory sync)",
    )
    job_id: str | None = Field(default=None, description="ARQ job ID")
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Sync start timestamp",
    )
    completed_at: datetime | None = Field(
        default=None, description="Sync completion timestamp"
    )
    duration_seconds: float | None = Field(
        default=None, description="Total sync duration in seconds"
    )
    statistics: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON), description="Sync statistics and metrics"
    )
    error_message: str | None = Field(
        default=None, description="Error details if sync failed"
    )
    created_by: UUID | None = Field(
        default=None, description="User ID who triggered manual sync"
    )


class IngramSyncLog(IngramSyncLogBase, table=True):
    """Database model for Ingram Micro sync logs"""

    __tablename__ = "ingram_sync_logs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Record creation timestamp",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Record last update timestamp",
    )


class IngramSyncLogCreate(IngramSyncLogBase):
    """Schema for creating new sync log"""

    pass


class IngramSyncLogUpdate(SQLModel):
    """Schema for updating sync log"""

    status: SyncStatus | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    statistics: dict[str, Any] | None = None
    error_message: str | None = None


class IngramSyncLogPublic(IngramSyncLogBase):
    """Public schema for sync log"""

    id: UUID
    created_at: datetime
    updated_at: datetime


class IngramSyncLogCollection(BaseModel):
    """Collection response for sync logs"""

    data: list[IngramSyncLogPublic]
    count: int


class IngramProductSyncStatus(BaseModel):
    """Model for individual product sync status"""

    sku: str = Field(description="Ingram SKU")
    product_id: UUID | None = Field(default=None, description="Local product ID")
    status: str = Field(description="Sync status for this product")
    action: str = Field(description="Action taken (created, updated, skipped, failed)")
    error: str | None = Field(default=None, description="Error message if sync failed")
    last_synced: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Last sync timestamp",
    )


# Product mapping for Ingram integration
class IngramProductMappingBase(SQLModel):
    """Base model for mapping Ingram SKUs to local products"""

    ingram_sku: str = Field(index=True, description="Ingram Micro SKU")
    local_product_id: UUID = Field(
        foreign_key="products.id",
        index=True,
        description="Local product ID",
    )
    vendor_part_number: str = Field(description="Manufacturer part number")
    manufacturer: str = Field(description="Product manufacturer")
    last_synced: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Last synchronization timestamp",
    )
    sync_enabled: bool = Field(default=True, description="Whether to sync this product")


class IngramProductMapping(IngramProductMappingBase, table=True):
    """Database model for Ingram product mapping"""

    __tablename__ = "ingram_product_mappings"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Record creation timestamp",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Record last update timestamp",
    )


class IngramProductMappingCreate(IngramProductMappingBase):
    """Schema for creating product mapping"""

    pass


class IngramProductMappingUpdate(SQLModel):
    """Schema for updating product mapping"""

    last_synced: datetime | None = None
    sync_enabled: bool | None = None


class IngramProductMappingPublic(IngramProductMappingBase):
    """Public schema for product mapping"""

    id: UUID
    created_at: datetime
    updated_at: datetime


# API request/response models
class SyncStatsModel(BaseModel):
    """Model for sync statistics"""

    total_fetched: int = Field(default=0, description="Total products fetched from API")
    new_products: int = Field(default=0, description="New products created")
    updated_products: int = Field(default=0, description="Existing products updated")
    skipped_products: int = Field(default=0, description="Products skipped")
    failed_products: int = Field(default=0, description="Products that failed to sync")
    inventory_updates: int = Field(default=0, description="Inventory levels updated")
    errors: int = Field(default=0, description="Total errors encountered")


class ManualSyncRequest(BaseModel):
    """Request model for manual sync operations"""

    sync_type: SyncType = Field(description="Type of sync to perform")
    categories: list[str] | None = Field(
        default=None, description="Categories to sync (for product sync)"
    )
    skus: list[str] | None = Field(
        default=None, description="Specific SKUs to process (for inventory sync)"
    )
    force_full_sync: bool = Field(
        default=False,
        description="Whether to perform full sync ignoring last sync time",
    )


class SyncJobResponse(BaseModel):
    """Response model for sync job operations"""

    job_id: str = Field(description="ARQ job ID")
    sync_log_id: UUID = Field(description="Database sync log record ID")
    status: SyncStatus = Field(description="Initial job status")
    estimated_duration_minutes: int | None = Field(
        default=None, description="Estimated completion time in minutes"
    )
    message: str = Field(description="Human-readable status message")
    created_at: datetime = Field(description="Job creation timestamp")
