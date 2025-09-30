"""
Consolidation and shipment grouping models.
Concrete operational grouping on a route.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy.dialects.postgresql import NUMERIC
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import JSON, Column, Field, Relationship, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate

if TYPE_CHECKING:
    pass


class ShippingRouteConsolidationBase(Base):
    """
    Concrete operational grouping on a route (e.g., daily flight/ship).
    Multiple orders are attached to it.
    """

    route_id: uuid.UUID = Field(
        foreign_key="shipping_routes.id", description="Parent route"
    )

    # Identification
    name: str = Field(
        max_length=200, description="Grouping name (e.g., AF076 2025-10-01)"
    )
    consolidation_code: str = Field(
        max_length=100, unique=True, index=True, description="Unique grouping code"
    )

    # Status
    status_code: str | None = Field(
        default="open", max_length=50, description="Grouping status"
    )
    is_done: bool = Field(default=False, description="Grouping completed")

    # Planned and actual schedules
    departure_planned_at: datetime | None = Field(
        default=None, description="Planned departure"
    )
    arrival_planned_at: datetime | None = Field(
        default=None, description="Planned arrival"
    )
    departure_actual_at: datetime | None = Field(
        default=None, description="Actual departure"
    )
    arrival_actual_at: datetime | None = Field(
        default=None, description="Actual arrival"
    )

    # Tracking references
    tracking_ref: str | None = Field(
        default=None, max_length=100, description="Carrier tracking reference"
    )

    # Grouping metrics
    total_packages: int = Field(default=0, description="Total number of packages")
    total_weight_kg: float = Field(default=0.0, description="Total weight in kg")
    total_volume_m3: float = Field(default=0.0, description="Total volume in m³")

    # Constraints and capacities
    max_packages: int | None = Field(
        default=None, description="Max number of packages"
    )
    max_weight_kg: float | None = Field(
        default=None, description="Max weight allowed"
    )
    max_volume_m3: float | None = Field(
        default=None, description="Max volume allowed"
    )

    # Deadline for adding orders
    cutoff_datetime: datetime | None = Field(
        default=None, description="Deadline for adding orders"
    )

    # Grouping costs
    total_cost: Decimal | None = Field(
        default=None, sa_column=Column(NUMERIC(12, 2)), description="Total cost"
    )
    currency: str | None = Field(default="EUR", max_length=3, description="Currency")

    # Specific constraints
    capacity_constraints: str | None = Field(
        default=None, sa_column=Column(JSON), description="Capacity constraints"
    )

    # Notes and metadata
    notes: str | None = Field(
        default=None, max_length=1000, description="Free notes"
    )
    consolidation_metadata: str | None = Field(
        default=None, sa_column=Column(JSON), description="Flexible metadata"
    )


class ShippingRouteConsolidation(ShippingRouteConsolidationBase, table=True):
    """Concrete operational grouping on a route"""

    __tablename__ = "shipping_route_consolidations"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True),
    )


class ShippingRouteConsolidationCreate(ShippingRouteConsolidationBase, BaseCreate):
    pass


class ShippingRouteConsolidationUpdate(ShippingRouteConsolidationBase, BaseUpdate):
    name: str | None = None
    status_code: str | None = None
    is_done: bool | None = None
    departure_planned_at: datetime | None = None
    arrival_planned_at: datetime | None = None
    departure_actual_at: datetime | None = None
    arrival_actual_at: datetime | None = None
    tracking_ref: str | None = None
    total_packages: int | None = None
    total_weight_kg: float | None = None
    total_volume_m3: float | None = None
    max_packages: int | None = None
    max_weight_kg: float | None = None
    max_volume_m3: float | None = None
    cutoff_datetime: datetime | None = None
    total_cost: Decimal | None = None
    currency: str | None = None
    capacity_constraints: str | None = None
    notes: str | None = None
    consolidation_metadata: str | None = None


class ShippingRouteConsolidationPublic(ShippingRouteConsolidationBase, BasePublic):
    id: uuid.UUID


class ShippingRouteConsolidationsPublic(SQLModel):
    data: list[ShippingRouteConsolidationPublic] = Field(
        default_factory=list,
        description="List of shipping route consolidations",
    )
    count: int = Field(
        default=0,
        description="Total number of shipping route consolidations",
    )


class ShippingOrderConsolidationBase(Base):
    """
    Serves as anchor for tracking and pricing audit.
    """

    consolidation_id: uuid.UUID = Field(
        foreign_key="shipping_route_consolidations.id",
        description="Parent consolidation",
    )
    order_id: uuid.UUID = Field(description="Order ID")

    # Physical quantities
    package_qty: int = Field(default=1, description="Number of packages")
    weight_kg: float | None = Field(default=None, description="Weight in kg")
    volume_m3: float | None = Field(default=None, description="Volume in m³")

    # Dimensions for single package
    length_m: float | None = Field(default=None, description="Length in m")
    width_m: float | None = Field(default=None, description="Width in m")
    height_m: float | None = Field(default=None, description="Height in m")

    # Agreed price when chosen by customer (replaces RateQuote)
    agreed_shipping_price: Decimal | None = Field(
        default=None, sa_column=Column(NUMERIC(12, 2)), description="Agreed price"
    )
    agreed_currency: str | None = Field(
        default="EUR", max_length=3, description="Agreed currency"
    )

    # Reservation metadata
    reserved_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Reservation date",
    )
    confirmed_at: datetime | None = Field(
        default=None, description="Confirmation date"
    )

    # Idempotency key to avoid duplicates
    idempotency_key: str | None = Field(
        default=None, max_length=100, description="Idempotency key"
    )

    # Link status
    status_code: str | None = Field(
        default="reserved", max_length=50, description="Link status"
    )

    # Notes
    notes: str | None = Field(
        default=None, max_length=500, description="Specific notes"
    )


class ShippingOrderConsolidation(ShippingOrderConsolidationBase, table=True):
    """Lien Commande → Consolidation"""

    __tablename__ = "shipping_order_consolidations"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True),
    )

    # Relations
    consolidation: ShippingRouteConsolidation = Relationship(
        back_populates="order_links", sa_relationship_kwargs={"lazy": "selectin"}
    )


class ShippingOrderConsolidationCreate(ShippingOrderConsolidationBase, BaseCreate):
    pass


class ShippingOrderConsolidationUpdate(ShippingOrderConsolidationBase, BaseUpdate):
    package_qty: int | None = None
    weight_kg: float | None = None
    volume_m3: float | None = None
    length_m: float | None = None
    width_m: float | None = None
    height_m: float | None = None
    agreed_shipping_price: Decimal | None = None
    agreed_currency: str | None = None
    confirmed_at: datetime | None = None
    status_code: str | None = None
    notes: str | None = None


class ShippingOrderConsolidationPublic(ShippingOrderConsolidationBase, BasePublic):
    id: uuid.UUID


class ShippingOrderConsolidationsPublic(SQLModel):
    data: list[ShippingOrderConsolidationPublic] = Field(
        default_factory=list,
        description="List of shipping order consolidations",
    )
    count: int = Field(
        default=0,
        description="Total number of shipping order consolidations",
    )


class ShippingRouteConsolidationsPublic(SQLModel):
    data: list[ShippingRouteConsolidationPublic] = Field(
        default_factory=list,
        description="List of shipping route consolidations",
    )
    count: int = Field(
        default=0,
        description="Total number of shipping route consolidations",
    )


class ShippingOrderConsolidationsPublic(SQLModel):
    data: list[ShippingOrderConsolidationPublic] = Field(
        default_factory=list,
        description="List of shipping order consolidations",
    )
    count: int = Field(
        default=0,
        description="Total number of shipping order consolidations",
    )


class ShippingOrderStepConsolidationBase(Base):
    """Suivi d'une commande pour une Ã©tape donnÃ©e (scan, statut, preuve)"""

    consolidation_id: uuid.UUID = Field(
        foreign_key="shipping_route_consolidations.id", description="Consolidation"
    )
    route_step_id: uuid.UUID = Field(
        foreign_key="shipping_route_steps.id", description="Ã‰tape de route"
    )
    order_id: uuid.UUID = Field(description="Order ID")

    # Statut pour cette étape spécifique
    status_code: str | None = Field(
        default="pending", max_length=50, description="Statut de l'étape"
    )
    is_done: bool = Field(default=False, description="Étape terminée")

    # Suivi
    scan_ref: str | None = Field(
        default=None, max_length=100, description="Référence de scan"
    )
    tracking_number: str | None = Field(
        default=None, max_length=100, description="Numéro de suivi transporteur"
    )

    # Timeline
    occurred_at: datetime | None = Field(
        default=None, description="Quand l'Ã©vÃ©nement s'est produit"
    )
    last_event_at: datetime | None = Field(
        default=None, description="Dernier Ã©vÃ©nement enregistrÃ©"
    )

    # Preuves
    evidence_url: str | None = Field(
        default=None, max_length=500, description="URL de preuve"
    )
    signature_name: str | None = Field(
        default=None, max_length=100, description="Nom du signataire"
    )
    actor: str | None = Field(
        default=None, max_length=100, description="Acteur ayant effectuÃ© l'action"
    )

    # Notes
    notes: str | None = Field(
        default=None, max_length=500, description="Notes spÃ©cifiques Ã  cette Ã©tape"
    )


class ShippingOrderStepConsolidation(ShippingOrderStepConsolidationBase, table=True):
    """Suivi d'une commande pour une étape donnée"""

    __tablename__ = "shipping_order_step_consolidations"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True),
    )


class ShippingOrderStepConsolidationCreate(
    ShippingOrderStepConsolidationBase, BaseCreate
):
    pass


class ShippingOrderStepConsolidationUpdate(
    ShippingOrderStepConsolidationBase, BaseUpdate
):
    status_code: str | None = None
    is_done: bool | None = None
    scan_ref: str | None = None
    tracking_number: str | None = None
    occurred_at: datetime | None = None
    last_event_at: datetime | None = None
    evidence_url: str | None = None
    signature_name: str | None = None
    actor: str | None = None
    notes: str | None = None


class ShippingOrderStepConsolidationPublic(
    ShippingOrderStepConsolidationBase, BasePublic
):
    id: uuid.UUID


class ShippingOrderStepConsolidationsPublic(SQLModel):
    data: list[ShippingOrderStepConsolidationPublic] = Field(
        default_factory=list,
        description="List of shipping order step consolidations",
    )
    count: int = Field(
        default=0,
        description="Total number of shipping order step consolidations",
    )


class ShippingOrderStepConsolidationsPublic(SQLModel):
    data: list[ShippingOrderStepConsolidationPublic] = Field(
        default_factory=list,
        description="List of shipping order step consolidations",
    )
    count: int = Field(
        default=0,
        description="Total number of shipping order step consolidations",
    )
