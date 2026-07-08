"""
Zones served by a shipping route.

A last-leg route (fret bateau, fret aérien...) can serve several geographic
zones at once (islands, municipalities, whole archipelagos): one row per
served zone. Thanks to the place hierarchy, serving a parent zone (e.g. the
Tuamotu archipelago) covers every child zone without enumerating them.
"""

import uuid

from sqlalchemy import Column, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel

from app.features.place.models import PlacePublic


class RouteServedPlace(SQLModel, table=True):
    """Represents a zone served by a shipping route."""

    __tablename__ = "route_served_places"
    __table_args__ = (
        UniqueConstraint("route_id", "place_id", name="uq_route_served_place"),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True),
    )
    route_id: uuid.UUID = Field(
        foreign_key="shipping_routes.id",
        index=True,
        description="Shipping route",
    )
    place_id: uuid.UUID = Field(
        foreign_key="places.id",
        index=True,
        description="Served zone (island, municipality, archipelago...)",
    )


class RouteServedPlacesUpdate(SQLModel):
    """Replace the set of zones served by a route."""

    place_ids: list[uuid.UUID] = Field(
        default_factory=list,
        description="Full list of served zone ids (replaces existing)",
    )


class RouteServedPlacesPublic(SQLModel):
    """Zones served by a route."""

    route_id: uuid.UUID
    places: list[PlacePublic] = Field(default_factory=list)
