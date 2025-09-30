"""
Modèles de routes de livraison.
Route logistique réutilisable et ses étapes.
"""

import uuid
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from decimal import Decimal

from sqlmodel import Field, Relationship, SQLModel, Column, JSON
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, NUMERIC

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate

if TYPE_CHECKING:
    from app.features.shipping.models.partner import Partner
    from app.features.shipping.models.place import Place
    from app.features.shipping.models.consolidation import ShippingRouteConsolidation


class ShippingRouteBase(Base):
    """Route logistique réutilisable (ex: France → Tahiti, Tahiti → Rangiroa)"""
    
    # Origine / destination
    from_place_id: uuid.UUID = Field(foreign_key="places.id", description="Lieu d'origine")
    to_place_id: uuid.UUID = Field(foreign_key="places.id", description="Lieu de destination")
    from_partner_id: Optional[uuid.UUID] = Field(default=None, foreign_key="partners.id", description="Partenaire origine (ex: fournisseur)")
    to_partner_id: Optional[uuid.UUID] = Field(default=None, foreign_key="partners.id", description="Partenaire destination (ex: client)")
    
    # Caractéristiques de la route
    name: str = Field(max_length=200, description="Nom de la route")
    description: Optional[str] = Field(default=None, max_length=500, description="Description de la route")
    
    # Types de route
    is_to_customer: bool = Field(default=False, description="Route vers client final")
    allow_consolidation: bool = Field(default=True, description="Permet regroupement de colis")
    
    # Mode de transport principal
    mode: str = Field(max_length=50, description="Mode: air, sea, road, pickup")
    operator: Optional[str] = Field(default=None, max_length=100, description="Opérateur (Air France, Navire X)")
    operator_ref: Optional[str] = Field(default=None, max_length=100, description="Référence vol/BL/booking")
    
    # Tarifs & empreinte (globaux optionnels)
    base_price: Optional[Decimal] = Field(default=None, sa_column=Column(NUMERIC(12, 2)), description="Prix de base")
    price_per_kg: Optional[Decimal] = Field(default=None, sa_column=Column(NUMERIC(10, 2)), description="Prix par kg")
    carbon_footprint_kg_co2e: Optional[float] = Field(default=None, description="Empreinte carbone kg CO2e")
    eta_days: Optional[int] = Field(default=None, description="Délai estimé en jours")
    
    # Contraintes
    max_weight_kg: Optional[float] = Field(default=None, description="Poids maximum autorisé")
    max_volume_m3: Optional[float] = Field(default=None, description="Volume maximum autorisé")
    max_dimensions_m: Optional[str] = Field(default=None, sa_column=Column(JSON), description="Dimensions max {length, width, height}")
    
    # Statut et gestion
    status_code: Optional[str] = Field(default="draft", max_length=50, description="Statut actuel")
    priority: int = Field(default=0, description="Priorité d'affichage")
    
    # Horaires et fréquence
    frequency_days: Optional[int] = Field(default=None, description="Fréquence en jours")
    departure_time: Optional[str] = Field(default=None, max_length=10, description="Heure de départ (HH:MM)")
    
    # Notes et métadonnées
    notes: Optional[str] = Field(default=None, max_length=1000, description="Notes libres")
    route_metadata: Optional[str] = Field(default=None, sa_column=Column(JSON), description="Métadonnées flexibles")


class ShippingRoute(ShippingRouteBase, table=True):
    """Route logistique réutilisable"""
    __tablename__ = "shipping_routes"
    
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True)
    )
    
    # Relations
    from_place: "Place" = Relationship(
        back_populates="origin_routes",
        sa_relationship_kwargs={"foreign_keys": "[ShippingRoute.from_place_id]", "lazy": "selectin"}
    )
    to_place: "Place" = Relationship(
        back_populates="destination_routes", 
        sa_relationship_kwargs={"foreign_keys": "[ShippingRoute.to_place_id]", "lazy": "selectin"}
    )
    from_partner: Optional["Partner"] = Relationship(
        back_populates="origin_routes",
        sa_relationship_kwargs={"foreign_keys": "[ShippingRoute.from_partner_id]", "lazy": "selectin"}
    )
    to_partner: Optional["Partner"] = Relationship(
        back_populates="destination_routes",
        sa_relationship_kwargs={"foreign_keys": "[ShippingRoute.to_partner_id]", "lazy": "selectin"}
    )
    
    steps: List["ShippingRouteStep"] = Relationship(
        back_populates="route",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "lazy": "selectin"}
    )
    consolidations: List["ShippingRouteConsolidation"] = Relationship(
        back_populates="route",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "lazy": "selectin"}
    )


class ShippingRouteCreate(ShippingRouteBase, BaseCreate):
    pass


class ShippingRouteUpdate(ShippingRouteBase, BaseUpdate):
    from_place_id: Optional[uuid.UUID] = None
    to_place_id: Optional[uuid.UUID] = None
    from_partner_id: Optional[uuid.UUID] = None
    to_partner_id: Optional[uuid.UUID] = None
    name: Optional[str] = None
    description: Optional[str] = None
    is_to_customer: Optional[bool] = None
    allow_consolidation: Optional[bool] = None
    mode: Optional[str] = None
    operator: Optional[str] = None
    operator_ref: Optional[str] = None
    base_price: Optional[Decimal] = None
    price_per_kg: Optional[Decimal] = None
    carbon_footprint_kg_co2e: Optional[float] = None
    eta_days: Optional[int] = None
    max_weight_kg: Optional[float] = None
    max_volume_m3: Optional[float] = None
    max_dimensions_m: Optional[str] = None
    status_code: Optional[str] = None
    priority: Optional[int] = None
    frequency_days: Optional[int] = None
    departure_time: Optional[str] = None
    notes: Optional[str] = None
    route_metadata: Optional[str] = None


class ShippingRoutePublic(ShippingRouteBase, BasePublic):
    id: uuid.UUID


class ShippingRouteStepBase(Base):
    """Étape séquencée à l'intérieur d'une route (ex: CDG→PPT)"""
    
    route_id: uuid.UUID = Field(foreign_key="shipping_routes.id", description="Route parente")
    sequence: int = Field(description="Ordre de l'étape dans la route")
    
    # Lieux de départ et d'arrivée
    from_place_id: uuid.UUID = Field(foreign_key="places.id", description="Lieu de départ")
    to_place_id: uuid.UUID = Field(foreign_key="places.id", description="Lieu d'arrivée")

    # Transport pour cette étape
    mode: str = Field(max_length=50, description="Mode de transport: air, sea, road")
    operator: Optional[str] = Field(default=None, max_length=100, description="Opérateur")
    operator_ref: Optional[str] = Field(default=None, max_length=100, description="Référence vol/BL/etc")
    
    # Coûts et délais pour cette étape
    step_price: Optional[Decimal] = Field(default=None, sa_column=Column(NUMERIC(12, 2)), description="Prix de cette étape")
    carbon_footprint_kg_co2e: Optional[float] = Field(default=None, description="Empreinte carbone de l'étape")
    eta_days: Optional[int] = Field(default=None, description="Délai de cette étape")
    
    # Horaires
    departure_time: Optional[str] = Field(default=None, max_length=10, description="Heure de départ")
    arrival_time: Optional[str] = Field(default=None, max_length=10, description="Heure d'arrivée")
    
    # Statut de l'étape
    status_code: Optional[str] = Field(default="draft", max_length=50, description="Statut de l'étape")
    
    # Notes
    notes: Optional[str] = Field(default=None, max_length=500, description="Notes pour cette étape")


class ShippingRouteStep(ShippingRouteStepBase, table=True):
    """Étape séquencée à l'intérieur d'une route"""
    __tablename__ = "shipping_route_steps"
    
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True)
    )
    
    # Relations
    route: ShippingRoute = Relationship(
        back_populates="steps",
        sa_relationship_kwargs={"lazy": "selectin"}
    )
    from_place: "Place" = Relationship(
        back_populates="departure_steps",
        sa_relationship_kwargs={"foreign_keys": "[ShippingRouteStep.from_place_id]", "lazy": "selectin"}
    )
    to_place: "Place" = Relationship(
        back_populates="arrival_steps",
        sa_relationship_kwargs={"foreign_keys": "[ShippingRouteStep.to_place_id]", "lazy": "selectin"}
    )


class ShippingRouteStepCreate(ShippingRouteStepBase, BaseCreate):
    pass


class ShippingRouteStepUpdate(ShippingRouteStepBase, BaseUpdate):
    sequence: Optional[int] = None
    from_place_id: Optional[uuid.UUID] = None
    to_place_id: Optional[uuid.UUID] = None
    mode: Optional[str] = None
    operator: Optional[str] = None
    operator_ref: Optional[str] = None
    step_price: Optional[Decimal] = None
    carbon_footprint_kg_co2e: Optional[float] = None
    eta_days: Optional[int] = None
    departure_time: Optional[str] = None
    arrival_time: Optional[str] = None
    status_code: Optional[str] = None
    notes: Optional[str] = None


class ShippingRouteStepPublic(ShippingRouteStepBase, BasePublic):
    id: uuid.UUID


class ShippingRoutesPublic(SQLModel):
    data: list[ShippingRoutePublic] = Field(
        default_factory=list,
        description="List of shipping routes",
    )
    count: int = Field(
        default=0,
        description="Total number of shipping routes",
    )


class ShippingRouteStepsPublic(SQLModel):
    data: list[ShippingRouteStepPublic] = Field(
        default_factory=list,
        description="List of shipping route steps",
    )
    count: int = Field(
        default=0,
        description="Total number of shipping route steps",
    )