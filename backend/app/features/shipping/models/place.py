"""
Modèles de lieux physiques.
Tout lieu physique (aéroport, port, entrepôt, adresse client, île...).
"""

import uuid
from typing import Optional, List, TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate

if TYPE_CHECKING:
    from app.features.shipping.models.shipping_route import ShippingRoute, ShippingRouteStep
    from app.features.shipping.models.delivery_task import DeliveryTask


class PlaceBase(Base):
    """Tout lieu physique (aéroport, port, entrepôt, adresse client, île...)"""
    name: str = Field(max_length=200, description="Nom du lieu")
    type: str = Field(max_length=50, description="Type: airport, seaport, warehouse, address, island, etc.")
    code: Optional[str] = Field(default=None, max_length=50, description="Code IATA/UN/LOCODE/autre")
    
    # Géolocalisation
    latitude: Optional[float] = Field(default=None, description="Latitude")
    longitude: Optional[float] = Field(default=None, description="Longitude")
    timezone: Optional[str] = Field(default=None, max_length=50, description="Fuseau horaire")
    
    # Adresse complète
    address_line1: Optional[str] = Field(default=None, max_length=200)
    address_line2: Optional[str] = Field(default=None, max_length=200)
    city: Optional[str] = Field(default=None, max_length=100)
    postal_code: Optional[str] = Field(default=None, max_length=20)
    country: Optional[str] = Field(default=None, max_length=2, description="Code pays ISO")
    region: Optional[str] = Field(default=None, max_length=100, description="Région/État")
    
    # Capacités pour entrepôts
    is_warehouse: bool = Field(default=False, description="Est un entrepôt")
    max_capacity_m3: Optional[float] = Field(default=None, description="Capacité max en m³")
    current_capacity_m3: Optional[float] = Field(default=None, description="Capacité actuelle en m³")
    
    # Services disponibles
    customs_clearance: bool = Field(default=False, description="Dédouanement disponible")
    consolidation_service: bool = Field(default=False, description="Service de consolidation")
    repackaging_service: bool = Field(default=False, description="Service de reconditionnement")
    
    # Horaires d'opération
    operating_hours: Optional[str] = Field(default=None, max_length=50, description="Horaires d'ouverture")


class Place(PlaceBase, table=True):
    """Tout lieu physique (aéroport, port, entrepôt, adresse client, île...)"""
    __tablename__ = "places"
    
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True)
    )
    
    # Relations
    origin_routes: List["ShippingRoute"] = Relationship(
        back_populates="from_place",
        sa_relationship_kwargs={"foreign_keys": "[ShippingRoute.from_place_id]", "lazy": "selectin"}
    )
    destination_routes: List["ShippingRoute"] = Relationship(
        back_populates="to_place",
        sa_relationship_kwargs={"foreign_keys": "[ShippingRoute.to_place_id]", "lazy": "selectin"}
    )
    departure_steps: List["ShippingRouteStep"] = Relationship(
        back_populates="from_place",
        sa_relationship_kwargs={"foreign_keys": "[ShippingRouteStep.from_place_id]", "lazy": "selectin"}
    )
    arrival_steps: List["ShippingRouteStep"] = Relationship(
        back_populates="to_place",
        sa_relationship_kwargs={"foreign_keys": "[ShippingRouteStep.to_place_id]", "lazy": "selectin"}
    )
    delivery_tasks: List["DeliveryTask"] = Relationship(
        back_populates="address_place",
        sa_relationship_kwargs={"lazy": "selectin"}
    )


class PlaceCreate(PlaceBase, BaseCreate):
    pass


class PlaceUpdate(PlaceBase, BaseUpdate):
    name: Optional[str] = None
    type: Optional[str] = None
    code: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    timezone: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    region: Optional[str] = None
    is_warehouse: Optional[bool] = None
    max_capacity_m3: Optional[float] = None
    current_capacity_m3: Optional[float] = None
    customs_clearance: Optional[bool] = None
    consolidation_service: Optional[bool] = None
    repackaging_service: Optional[bool] = None
    operating_hours: Optional[str] = None


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