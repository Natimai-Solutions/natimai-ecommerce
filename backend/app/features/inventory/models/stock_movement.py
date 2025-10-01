import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Column, Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class MovementType(str, Enum):
    """Enumeration for stock movement types."""

    INCOMING = "incoming"
    OUTGOING = "outgoing"
    TRANSFER = "transfer"
    ADJUSTMENT = "adjustment"


class ReferenceType(str, Enum):
    """Enumeration for movement reference types."""

    ORDER = "order"
    MANUAL = "manual"
    SYSTEM = "system"
    CORRECTION = "correction"


class MovementStatus(str, Enum):
    """Enumeration for movement status."""

    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class InventoryStockMovementBase(Base):
    """Base model for inventory stock movement with common attributes."""

    # Movement identification
    movement_type: str = Field(
        description="Type of stock movement (incoming, outgoing, transfer, adjustment)"
    )
    reference_type: str = Field(
        description="Reference type for the movement (order, manual, system, correction)"
    )
    reference_id: uuid.UUID | None = Field(
        default=None, description="Reference ID (order, manual entry, etc.)"
    )

    # Location details
    from_place_id: uuid.UUID | None = Field(
        default=None, foreign_key="places.id", description="Departure place ID"
    )
    to_place_id: uuid.UUID | None = Field(
        default=None, foreign_key="places.id", description="Arrival place ID"
    )

    # Product and quantity
    product_id: uuid.UUID = Field(
        foreign_key="products.id", description="Product being moved"
    )
    quantity: int = Field(gt=0, description="Quantity moved")
    unit_cost: float | None = Field(
        default=None, ge=0, description="Unit cost at time of movement"
    )

    # Movement details
    reason: str | None = Field(
        default=None, max_length=500, description="Reason for the movement"
    )
    notes: str | None = Field(
        default=None, max_length=1000, description="Additional notes"
    )

    # Status and tracking
    status: str = Field(
        default="pending",
        description="Movement status (pending, completed, cancelled, failed)",
    )
    processed_at: datetime | None = Field(
        default=None, description="When the movement was processed"
    )


class InventoryStockMovement(InventoryStockMovementBase, table=True):
    """Inventory stock movement table model."""

    __tablename__ = "inventory_stock_movements"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True),
    )


class InventoryStockMovementCreate(InventoryStockMovementBase, BaseCreate):
    """Schema for creating a new inventory stock movement."""

    # Override required fields for creation
    movement_type: str = Field(
        description="Movement type (incoming, outgoing, transfer, adjustment)"
    )
    reference_type: str = Field(
        description="Reference type (order, manual, system, correction)"
    )
    product_id: uuid.UUID
    quantity: int = Field(gt=0, description="Quantity moved")

    # Optional fields can remain as inherited


class InventoryStockMovementUpdate(BaseUpdate):
    """Schema for updating an inventory stock movement."""

    # Movement identification
    movement_type: str | None = Field(default=None, description="Movement type")
    reference_type: str | None = Field(default=None, description="Reference type")
    reference_id: uuid.UUID | None = None

    # Location details
    from_place_id: uuid.UUID | None = None
    to_place_id: uuid.UUID | None = None

    # Product and quantity
    product_id: uuid.UUID | None = None
    quantity: int | None = Field(default=None, gt=0, description="Quantity moved")
    unit_cost: float | None = Field(default=None, ge=0, description="Unit cost")

    # Movement details
    reason: str | None = Field(default=None, max_length=500, description="Reason")
    notes: str | None = Field(default=None, max_length=1000, description="Notes")

    # Status and tracking
    status: str | None = Field(default=None, description="Movement status")
    processed_at: datetime | None = None


class InventoryStockMovementPublic(InventoryStockMovementBase, BasePublic):
    """Public schema for inventory stock movement responses."""

    id: uuid.UUID
    movement_type: str
    reference_type: str
    product_id: uuid.UUID
    quantity: int
    status: str


# Collection schemas
class InventoryStockMovementsPublic(SQLModel):
    """Schema for multiple inventory stock movements response."""

    data: list[InventoryStockMovementPublic] = Field(
        default_factory=list, description="List of inventory stock movements"
    )
    count: int = Field(
        default=0, description="Total number of inventory stock movements"
    )
