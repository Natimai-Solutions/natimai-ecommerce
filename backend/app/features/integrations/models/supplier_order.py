"""Model for tracking supplier purchase orders created on behalf of local orders."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from sqlmodel import JSON, Column, Field, SQLModel


class SupplierOrderStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    ERROR = "error"
    SKIPPED = "skipped"


class SupplierOrder(SQLModel, table=True):
    """Tracks one Ingram Micro (or other supplier) PO per local order."""

    __tablename__ = "supplier_orders"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    supplier_name: str = Field(
        index=True,
        description="Machine name of the supplier (e.g. 'ingram_micro')",
    )
    local_order_id: UUID = Field(
        foreign_key="orders.id",
        index=True,
        description="Local order that triggered this PO",
    )
    customer_order_number: str = Field(
        index=True,
        description="Reference sent to the supplier (local order UUID, deduplicated by Ingram)",
    )
    supplier_order_number: str | None = Field(
        default=None,
        index=True,
        description="PO number returned by the supplier (e.g. ingramOrderNumber)",
    )
    status: SupplierOrderStatus = Field(
        default=SupplierOrderStatus.PENDING,
        index=True,
    )
    supplier_status_label: str | None = Field(
        default=None,
        description="Raw status string from the supplier response",
    )
    lines_snapshot: list[dict[str, Any]] | None = Field(
        default=None,
        sa_column=Column(JSON),
        description="Lines sent to the supplier",
    )
    supplier_response: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSON),
        description="Full supplier response payload",
    )
    error_message: str | None = Field(default=None)
    attempts: int = Field(default=0)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )


class SupplierOrderPublic(SQLModel):
    """Public schema for supplier orders (admin endpoints)."""

    id: UUID
    supplier_name: str
    local_order_id: UUID
    customer_order_number: str
    supplier_order_number: str | None
    status: SupplierOrderStatus
    supplier_status_label: str | None
    error_message: str | None
    attempts: int
    created_at: datetime
    updated_at: datetime


class SupplierOrdersPublic(SQLModel):
    data: list[SupplierOrderPublic] = Field(default_factory=list)
    count: int = 0
