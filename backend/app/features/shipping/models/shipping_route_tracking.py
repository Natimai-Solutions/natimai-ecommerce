
"""
Shipping route tracking models.
Tracks customer's route choices and status for orders.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from pydantic import computed_field
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, Relationship, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate

if TYPE_CHECKING:
    from app.features.shipping.models.shipping_route import ShippingRoute
    from app.features.shipping.models.status import StatusDefinition
    from app.features.place.models import Place


class ShippingRouteTrackingBase(Base):
    """
    Tracks customer's selected route for an order.
    Replaces TrackingEvent with order-centric tracking.
    """

    order_id: uuid.UUID = Field(description="Order ID being tracked")
    route_id: uuid.UUID = Field(
        foreign_key="shipping_routes.id", description="Selected shipping route"
    )

    # Current status (relation to StatusDefinition)
    status_id: uuid.UUID = Field(
        foreign_key="status_definitions.id", 
        description="Current status (references StatusDefinition)"
    )

    # Consolidation link (optional)
    consolidation_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="shipping_route_tracking_consolidations.id",
        description="Linked consolidation if grouped",
    )

    # Route selection details
    selected_at: datetime = Field(description="When route was selected by customer")
    
    # Multi-route sequencing
    sequence_order: int = Field(
        default=1,
        description="Order of this route in multi-hop journey (1=first, 2=second, etc.)"
    )
    
    # Status tracking
    last_status_update: datetime | None = Field(
        default=None, description="Last status update timestamp"
    )

    # Tracking reference
    tracking_ref: str | None = Field(
        default=None, max_length=100, description="Carrier tracking reference"
    )

    # Expected delivery
    estimated_delivery: datetime | None = Field(
        default=None, description="Estimated delivery date"
    )

    # Notes
    notes: str | None = Field(
        default=None, max_length=500, description="Tracking notes"
    )


class ShippingRouteTracking(ShippingRouteTrackingBase, table=True):
    """Customer's route selection and tracking for an order"""

    __tablename__ = "shipping_route_trackings"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True),
    )

    # Relations
    route: "ShippingRoute" = Relationship(
        sa_relationship_kwargs={
            "foreign_keys": "[ShippingRouteTracking.route_id]",
            "lazy": "selectin"
        }
    )
    status: "StatusDefinition" = Relationship(
        sa_relationship_kwargs={
            "foreign_keys": "[ShippingRouteTracking.status_id]",
            "lazy": "selectin"
        }
    )
    consolidation: Optional["ShippingRouteTrackingConsolidation"] = Relationship(
        sa_relationship_kwargs={
            "foreign_keys": "[ShippingRouteTracking.consolidation_id]",
            "lazy": "selectin"
        }
    )

    @computed_field
    @property
    def is_terminal(self) -> bool:
        if self.consolidation and self.consolidation.status:
            consolidation_is_terminal = self.consolidation.status.is_terminal
            if consolidation_is_terminal is not None:
                return consolidation_is_terminal
        if self.status:
            return self.status.is_terminal




class ShippingRouteTrackingCreate(ShippingRouteTrackingBase, BaseCreate):
    pass


class ShippingRouteTrackingUpdate(BaseUpdate):
    status_id: uuid.UUID | None = None
    consolidation_id: uuid.UUID | None = None
    sequence_order: int | None = None
    last_status_update: datetime | None = None
    tracking_ref: str | None = None
    estimated_delivery: datetime | None = None
    notes: str | None = None


class ShippingRouteTrackingPublic(ShippingRouteTrackingBase, BasePublic):
    id: uuid.UUID


class ShippingRouteTrackingConsolidationBase(Base):
    """
    Consolidation grouping for route trackings.
    When consolidated, status comes from this consolidation.
    """

    route_id: uuid.UUID = Field(
        foreign_key="shipping_routes.id", description="Parent route"
    )

    # Identification
    name: str = Field(
        max_length=200, description="Consolidation name"
    )
    consolidation_code: str = Field(
        max_length=100, unique=True, index=True, description="Unique consolidation code"
    )

    # Status (overrides individual tracking status when consolidated)
    status_id: uuid.UUID = Field(
        foreign_key="status_definitions.id", description="Consolidation status"
    )

    # Tracking
    tracking_ref: str | None = Field(
        default=None, max_length=100, description="Carrier tracking reference"
    )

    # Metrics
    total_orders: int = Field(default=0, description="Total number of orders")

    # Notes
    notes: str | None = Field(
        default=None, max_length=500, description="Consolidation notes"
    )


class ShippingRouteTrackingConsolidation(ShippingRouteTrackingConsolidationBase, table=True):
    """Consolidation for route trackings"""

    __tablename__ = "shipping_route_tracking_consolidations"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True),
    )

    # Relations
    route: "ShippingRoute" = Relationship(
        sa_relationship_kwargs={
            "foreign_keys": "[ShippingRouteTrackingConsolidation.route_id]",
            "lazy": "selectin"
        }
    )
    status: "StatusDefinition" = Relationship(
        sa_relationship_kwargs={
            "foreign_keys": "[ShippingRouteTrackingConsolidation.status_id]",
            "lazy": "selectin"
        }
    )


class ShippingRouteTrackingConsolidationCreate(ShippingRouteTrackingConsolidationBase, BaseCreate):
    pass


class ShippingRouteTrackingConsolidationUpdate(BaseUpdate):
    name: str | None = None
    status_id: uuid.UUID | None = None
    tracking_ref: str | None = None
    total_orders: int | None = None
    notes: str | None = None


class ShippingRouteTrackingConsolidationPublic(ShippingRouteTrackingConsolidationBase, BasePublic):
    id: uuid.UUID


# Collections
class ShippingRouteTrackingsPublic(SQLModel):
    data: list[ShippingRouteTrackingPublic] = Field(
        default_factory=list,
        description="List of shipping route trackings",
    )
    count: int = Field(
        default=0,
        description="Total number of shipping route trackings",
    )


class ShippingRouteTrackingConsolidationsPublic(SQLModel):
    data: list[ShippingRouteTrackingConsolidationPublic] = Field(
        default_factory=list,
        description="List of shipping route tracking consolidations",
    )
    count: int = Field(
        default=0,
        description="Total number of shipping route tracking consolidations",
    )


# Status History/Logs Model
class ShippingRouteTrackingLogsBase(Base):
    """
    Complete history of status changes for route tracking.
    Tracks all status transitions including consolidation overrides.
    """

    tracking_id: uuid.UUID = Field(
        foreign_key="shipping_route_trackings.id", 
        description="Route tracking entry"
    )
    
    # Status change details
    from_status_id: uuid.UUID | None = Field(
        default=None, 
        foreign_key="status_definitions.id",
        description="Previous status (null for initial)"
    )
    to_status_id: uuid.UUID = Field(
        foreign_key="status_definitions.id", 
        description="New status"
    )
    
    # Change context
    change_type: str = Field(
        max_length=50, 
        description="Type: direct, consolidation_override, auto_advance, manual"
    )
    
    # Consolidation context (if applicable)
    consolidation_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="shipping_route_tracking_consolidations.id",
        description="Consolidation that triggered change (if applicable)"
    )
    
    # Change metadata
    changed_by: str | None = Field(
        default=None, max_length=100, description="User or system that made change"
    )
    reason: str | None = Field(
        default=None, max_length=500, description="Reason for status change"
    )
    
    # Automatic transition info
    transition_id: uuid.UUID | None = Field(
        default=None, description="StatusTransition used (if applicable)"
    )
    was_auto_advance: bool = Field(
        default=False, description="Was this an automatic transition?"
    )
    required_confirmation: bool = Field(
        default=False, description="Did this transition require confirmation?"
    )


class ShippingRouteTrackingLogs(ShippingRouteTrackingLogsBase, table=True):
    """Status change history for route tracking"""

    __tablename__ = "shipping_route_tracking_logs"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True),
    )

    # Relations
    tracking: ShippingRouteTracking = Relationship(
        sa_relationship_kwargs={"lazy": "selectin"}
    )
    from_status: Optional["StatusDefinition"] = Relationship(
        sa_relationship_kwargs={
            "foreign_keys": "[ShippingRouteTrackingLogs.from_status_id]",
            "lazy": "selectin"
        }
    )
    to_status: "StatusDefinition" = Relationship(
        sa_relationship_kwargs={
            "foreign_keys": "[ShippingRouteTrackingLogs.to_status_id]",
            "lazy": "selectin"
        }
    )
    consolidation: Optional[ShippingRouteTrackingConsolidation] = Relationship(
        sa_relationship_kwargs={"lazy": "selectin"}
    )


class ShippingRouteTrackingLogsCreate(ShippingRouteTrackingLogsBase, BaseCreate):
    pass


class ShippingRouteTrackingLogsUpdate(BaseUpdate):
    reason: str | None = None
    changed_by: str | None = None


class ShippingRouteTrackingLogsPublic(ShippingRouteTrackingLogsBase, BasePublic):
    id: uuid.UUID


class ShippingRouteTrackingLogsListPublic(SQLModel):
    data: list[ShippingRouteTrackingLogsPublic] = Field(
        default_factory=list,
        description="List of status change logs",
    )
    count: int = Field(
        default=0,
        description="Total number of status changes",
    )