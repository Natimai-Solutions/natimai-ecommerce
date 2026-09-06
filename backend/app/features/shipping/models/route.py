"""
Shipping route models.
Reusable logistics route and its steps.
"""

# mypy: disable-error-code="assignment,misc,override"

import uuid
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any, Optional

from pydantic import field_validator
from sqlalchemy.dialects.postgresql import NUMERIC
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import JSON, Column, Field, Relationship, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate

if TYPE_CHECKING:
    from app.features.partner.models import Partner
    from app.features.place.models import Place


class ShippingRouteBase(Base):
    """Reusable logistics route (ex: France → Tahiti, Tahiti → Rangiroa)"""

    # Origin / destination
    from_place_id: uuid.UUID = Field(
        foreign_key="places.id",
        index=True,
        description="Origin place",
    )
    to_place_id: uuid.UUID = Field(
        foreign_key="places.id",
        index=True,
        description="Destination place",
    )
    from_partner_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="partners.id",
        index=True,
        description="Origin partner (e.g., supplier)",
    )
    to_partner_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="partners.id",
        index=True,
        description="Destination partner (e.g., customer)",
    )

    # Route characteristics
    name: str = Field(max_length=200, description="Route name")
    description: str | None = Field(
        default=None, max_length=500, description="Route description"
    )

    # Route types
    is_to_customer: bool = Field(default=False, description="Route to final customer")
    allow_consolidation: bool = Field(
        default=True, description="Allows package consolidation"
    )

    # Main transport mode
    mode: str = Field(max_length=50, description="Mode: air, sea, road, pickup")
    operator: str | None = Field(
        default=None, max_length=100, description="Operator (Air France, Ship X)"
    )
    operator_ref: str | None = Field(
        default=None, max_length=100, description="Flight/BL/booking reference"
    )

    # Rates & footprint (optional global)
    base_price: Decimal | None = Field(
        default=None, sa_column=Column(NUMERIC(12, 2)), description="Base price"
    )
    price_per_kg: Decimal | None = Field(
        default=None, sa_column=Column(NUMERIC(10, 2)), description="Price per kg"
    )
    # Classic carrier grid: the weight part of the tariff by band instead of
    # linear per-kg. [{"max_kg": 1, "price": 5}, {"max_kg": 3, "price": 8},
    # {"max_kg": null, "price": 12}] — sorted ascending, an optional open last
    # band (max_kg null) covers everything heavier. Above the last bounded
    # band, price_per_kg bills the excess. Empty/null = linear per-kg.
    weight_bands: list[dict[str, Any]] | None = Field(
        default=None,
        sa_column=Column(JSON),
        description=(
            "Weight bands [{max_kg, price}] replacing price_per_kg × weight; "
            "null = linear per-kg pricing"
        ),
    )
    free_shipping_threshold: Decimal | None = Field(
        default=None,
        sa_column=Column(NUMERIC(12, 2)),
        description=(
            "Franco: the route is free once the shipment's declared value "
            "reaches this amount (reference currency). Null = never free."
        ),
    )
    carbon_footprint_kg_co2e: float | None = Field(
        default=None, description="Carbon footprint kg CO2e"
    )
    eta_days: int | None = Field(default=None, description="Estimated delay in days")

    # Constraints
    max_weight_kg: float | None = Field(
        default=None, description="Maximum weight allowed"
    )
    max_volume_m3: float | None = Field(
        default=None, description="Maximum volume allowed"
    )
    max_dimensions_m: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSON),
        description="Max dimensions {length, width, height}",
    )

    # Import-route identification (France → Papeete leg that enters CAF customs base)
    service_level: str | None = Field(
        default=None,
        max_length=50,
        index=True,
        description=(
            "Cross-corridor service-level key for import routes: "
            "rapide | economique | ecologique. Null = not an import route."
        ),
    )
    customer_label: str | None = Field(
        default=None,
        max_length=100,
        description="Dropdown label shown to the customer (e.g. 'Rapide (avion)')",
    )
    is_default_import: bool = Field(
        default=False,
        description="Pre-selected import route for anonymous / preference-less users",
    )
    last_leg_delivery_type: str | None = Field(
        default=None,
        max_length=50,
        index=True,
        description=(
            "For last-leg routes (is_to_customer=True): the delivery mode this "
            "route serves and prices — pickup | home_delivery | air_freight. "
            "Maps the checkout delivery_type to a priced route. Null = untyped."
        ),
    )
    always_available: bool = Field(
        default=False,
        description=(
            "Last-leg routes only: offered whatever the customer's destination "
            "(e.g. in-store pickup). Routes that are neither always_available "
            "nor linked to served zones remain visible everywhere (legacy)."
        ),
    )

    # Status and management
    status_code: str | None = Field(
        default="draft", max_length=50, description="Current status"
    )
    priority: int = Field(default=0, description="Display priority")

    # Schedules and frequency
    frequency_days: int | None = Field(default=None, description="Frequency in days")
    departure_time: str | None = Field(
        default=None, max_length=10, description="Departure time (HH:MM)"
    )

    # Notes and metadata
    notes: str | None = Field(default=None, max_length=1000, description="Free notes")
    route_metadata: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON), description="Flexible metadata"
    )

    @field_validator("weight_bands", mode="before")
    @classmethod
    def _normalize_weight_bands(cls, value: Any) -> list[dict[str, Any]] | None:
        """Validate and sort the weight grid (runs on Create/Update payloads)."""
        return normalize_weight_bands(value)


def normalize_weight_bands(value: Any) -> list[dict[str, Any]] | None:
    """Return a clean, ascending ``[{max_kg, price}]`` grid, or None when empty.

    Rules: ``price`` >= 0; ``max_kg`` > 0 or null (open band, at most one, and
    it must be the heaviest); no duplicate ``max_kg``. Values are stored as
    strings so the JSON column keeps decimal precision.
    """
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError("weight_bands must be a list of {max_kg, price}")

    bands: list[tuple[Decimal | None, Decimal]] = []
    for raw in value:
        if not isinstance(raw, dict):
            raise ValueError("each weight band must be an object {max_kg, price}")
        raw_max = raw.get("max_kg")
        raw_price = raw.get("price")
        try:
            max_kg = None if raw_max in (None, "") else Decimal(str(raw_max))
            price = Decimal(str(raw_price))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError("weight band max_kg/price must be numbers") from exc
        if max_kg is not None and max_kg <= 0:
            raise ValueError("weight band max_kg must be > 0")
        if price < 0:
            raise ValueError("weight band price must be >= 0")
        bands.append((max_kg, price))

    if not bands:
        return None
    open_bands = [b for b in bands if b[0] is None]
    if len(open_bands) > 1:
        raise ValueError("at most one open weight band (max_kg null)")
    bounded = sorted(
        (b for b in bands if b[0] is not None), key=lambda b: b[0] or Decimal("0")
    )
    if len({b[0] for b in bounded}) != len(bounded):
        raise ValueError("duplicate weight band max_kg")

    ordered = bounded + open_bands
    return [
        {"max_kg": None if max_kg is None else str(max_kg), "price": str(price)}
        for max_kg, price in ordered
    ]


class ShippingRoute(ShippingRouteBase, table=True):
    """Reusable logistics route"""

    __tablename__ = "shipping_routes"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True),
    )

    # Relations
    from_place: "Place" = Relationship(
        sa_relationship_kwargs={
            "foreign_keys": "[ShippingRoute.from_place_id]",
            "lazy": "selectin",
        }
    )
    to_place: "Place" = Relationship(
        sa_relationship_kwargs={
            "foreign_keys": "[ShippingRoute.to_place_id]",
            "lazy": "selectin",
        }
    )
    from_partner: Optional["Partner"] = Relationship(
        sa_relationship_kwargs={
            "foreign_keys": "[ShippingRoute.from_partner_id]",
            "lazy": "selectin",
        }
    )
    to_partner: Optional["Partner"] = Relationship(
        sa_relationship_kwargs={
            "foreign_keys": "[ShippingRoute.to_partner_id]",
            "lazy": "selectin",
        }
    )


class ShippingRouteCreate(ShippingRouteBase, BaseCreate):
    """Represents shipping route create."""

    pass


class ShippingRouteUpdate(ShippingRouteBase, BaseUpdate):
    """Represents shipping route update."""

    from_place_id: uuid.UUID | None = None
    to_place_id: uuid.UUID | None = None
    from_partner_id: uuid.UUID | None = None
    to_partner_id: uuid.UUID | None = None
    name: str | None = None
    description: str | None = None
    is_to_customer: bool | None = None
    allow_consolidation: bool | None = None
    mode: str | None = None
    operator: str | None = None
    operator_ref: str | None = None
    base_price: Decimal | None = None
    price_per_kg: Decimal | None = None
    weight_bands: list[dict[str, Any]] | None = None
    free_shipping_threshold: Decimal | None = None
    carbon_footprint_kg_co2e: float | None = None
    eta_days: int | None = None
    max_weight_kg: float | None = None
    max_volume_m3: float | None = None
    max_dimensions_m: dict[str, Any] | None = None
    service_level: str | None = None
    customer_label: str | None = None
    is_default_import: bool | None = None
    last_leg_delivery_type: str | None = None
    always_available: bool | None = None
    status_code: str | None = None
    priority: int | None = None
    frequency_days: int | None = None
    departure_time: str | None = None
    notes: str | None = None
    route_metadata: dict[str, Any] | None = None


class ShippingRoutePublic(ShippingRouteBase, BasePublic):
    """Represents shipping route public."""

    id: uuid.UUID


class ShippingRoutesPublic(SQLModel):
    """Represents shipping routes public."""

    data: list[ShippingRoutePublic] = Field(
        default_factory=list,
        description="List of shipping routes",
    )
    count: int = Field(
        default=0,
        description="Total number of shipping routes",
    )
