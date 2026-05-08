"""
Modèles de lieux physiques.
Tout lieu physique (aéroport, port, entrepôt, adresse client, île...).
"""

import uuid

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class PlaceBase(Base):
    """Tout lieu physique (aéroport, port, entrepôt, adresse client, île...)"""

    name: str = Field(max_length=200, description="Place name")
    type: str = Field(
        max_length=50,
        index=True,
        description="Type: airport, seaport, warehouse, address, island, etc.",
    )
    code: str | None = Field(
        default=None,
        max_length=50,
        index=True,
        description="Code IATA/UN/LOCODE/autre",
    )

    # Géolocalisation
    latitude: float | None = Field(default=None, description="Latitude")
    longitude: float | None = Field(default=None, description="Longitude")
    timezone: str | None = Field(default=None, max_length=50, description="Timezone")

    # Adresse complète
    address_line1: str | None = Field(default=None, max_length=200)
    address_line2: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=20)
    country: str | None = Field(
        default=None,
        max_length=2,
        index=True,
        description="Code Country ISO",
    )
    region: str | None = Field(default=None, max_length=100, description="Region/État")

    # Capacités pour entrepôts
    is_warehouse: bool = Field(
        default=False,
        index=True,
        description="Is a warehouse",
    )
    max_capacity_m3: float | None = Field(
        default=None, description="Capacité max en m³"
    )
    current_capacity_m3: float | None = Field(
        default=None, description="Capacité actuelle en m³"
    )

    # Services disponibles
    customs_clearance: bool = Field(
        default=False, description="Dédouanement disponible"
    )
    consolidation_service: bool = Field(
        default=False, description="Consolidation service"
    )
    repackaging_service: bool = Field(default=False, description="Repackaging service")

    # Horaires d'opération
    operating_hours: str | None = Field(
        default=None, max_length=50, description="Operating hours"
    )
    partner_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="partners.id",
        index=True,
        description="ID of the partner associated with this place",
    )
    is_owned: bool = Field(
        default=False, description="Indicates if the place is owned by the company"
    )


class Place(PlaceBase, table=True):
    """Tout lieu physique (aéroport, port, entrepôt, adresse client, île...)"""

    __tablename__ = "places"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True),
    )


class PlaceCreate(PlaceBase, BaseCreate):
    pass


class PlaceUpdate(PlaceBase, BaseUpdate):
    name: str | None = None
    type: str | None = None
    code: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    timezone: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    postal_code: str | None = None
    country: str | None = None
    region: str | None = None
    is_warehouse: bool | None = None
    max_capacity_m3: float | None = None
    current_capacity_m3: float | None = None
    customs_clearance: bool | None = None
    consolidation_service: bool | None = None
    repackaging_service: bool | None = None
    operating_hours: str | None = None


class PlacePublic(PlaceBase, BasePublic):
    id: uuid.UUID


class PlacesPublic(SQLModel):
    data: list[PlacePublic] = Field(
        default_factory=list,
        description="List of places",
    )
    count: int = Field(
        default=0,
        description="Total number of places",
    )
