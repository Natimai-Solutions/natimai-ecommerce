"""
ModÃ¨les de consolidation et regroupement d'expÃ©ditions.
Groupement opÃ©rationnel concret sur une route.
"""

import uuid
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from datetime import datetime
from decimal import Decimal

from sqlmodel import Field, Relationship, SQLModel, Column, JSON
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, NUMERIC

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate

if TYPE_CHECKING:
    from app.features.shipping.models.shipping_route import ShippingRoute


class ShippingRouteConsolidationBase(Base):
    """
    Groupement opÃ©rationnel concret sur une route (ex: le vol/bateau du jour).
    On y accroche plusieurs commandes.
    """
    
    route_id: uuid.UUID = Field(foreign_key="shipping_routes.id", description="Route parente")
    
    # Identification
    name: str = Field(max_length=200, description="Nom du regroupement (ex: AF076 2025-10-01)")
    consolidation_code: str = Field(max_length=100, unique=True, index=True, description="Code unique du regroupement")
    
    # Statut
    status_code: Optional[str] = Field(default="open", max_length=50, description="Statut du regroupement")
    is_done: bool = Field(default=False, description="Regroupement terminÃ©")
    
    # Horaires planifiÃ©s et rÃ©els
    departure_planned_at: Optional[datetime] = Field(default=None, description="DÃ©part planifiÃ©")
    arrival_planned_at: Optional[datetime] = Field(default=None, description="ArrivÃ©e planifiÃ©e")
    departure_actual_at: Optional[datetime] = Field(default=None, description="DÃ©part rÃ©el")
    arrival_actual_at: Optional[datetime] = Field(default=None, description="ArrivÃ©e rÃ©elle")
    
    # RÃ©fÃ©rences de suivi
    tracking_ref: Optional[str] = Field(default=None, max_length=100, description="RÃ©fÃ©rence de suivi transporteur")
    
    # MÃ©triques du regroupement
    total_packages: int = Field(default=0, description="Nombre total de colis")
    total_weight_kg: float = Field(default=0.0, description="Poids total en kg")
    total_volume_m3: float = Field(default=0.0, description="Volume total en mÂ³")
    
    # Contraintes et capacitÃ©s
    max_packages: Optional[int] = Field(default=None, description="Nombre max de colis")
    max_weight_kg: Optional[float] = Field(default=None, description="Poids max autorisÃ©")
    max_volume_m3: Optional[float] = Field(default=None, description="Volume max autorisÃ©")
    
    # Date limite pour ajout de commandes
    cutoff_datetime: Optional[datetime] = Field(default=None, description="Date limite d'ajout de commandes")
    
    # CoÃ»ts du regroupement
    total_cost: Optional[Decimal] = Field(default=None, sa_column=Column(NUMERIC(12, 2)), description="CoÃ»t total")
    currency: Optional[str] = Field(default="EUR", max_length=3, description="Devise")
    
    # Contraintes spÃ©cifiques
    capacity_constraints: Optional[str] = Field(default=None, sa_column=Column(JSON), description="Contraintes de capacitÃ©")
    
    # Notes et mÃ©tadonnÃ©es
    notes: Optional[str] = Field(default=None, max_length=1000, description="Notes libres")
    consolidation_metadata: Optional[str] = Field(default=None, sa_column=Column(JSON), description="MÃ©tadonnÃ©es flexibles")


class ShippingRouteConsolidation(ShippingRouteConsolidationBase, table=True):
    """Groupement opÃ©rationnel concret sur une route"""
    __tablename__ = "shipping_route_consolidations"
    
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True)
    )
    
    # Relations
    route: "ShippingRoute" = Relationship(
        back_populates="consolidations",
        sa_relationship_kwargs={"lazy": "selectin"}
    )
    order_links: List["ShippingOrderConsolidation"] = Relationship(
        back_populates="consolidation",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "lazy": "selectin"}
    )


class ShippingRouteConsolidationCreate(ShippingRouteConsolidationBase, BaseCreate):
    pass


class ShippingRouteConsolidationUpdate(ShippingRouteConsolidationBase, BaseUpdate):
    name: Optional[str] = None
    status_code: Optional[str] = None
    is_done: Optional[bool] = None
    departure_planned_at: Optional[datetime] = None
    arrival_planned_at: Optional[datetime] = None
    departure_actual_at: Optional[datetime] = None
    arrival_actual_at: Optional[datetime] = None
    tracking_ref: Optional[str] = None
    total_packages: Optional[int] = None
    total_weight_kg: Optional[float] = None
    total_volume_m3: Optional[float] = None
    max_packages: Optional[int] = None
    max_weight_kg: Optional[float] = None
    max_volume_m3: Optional[float] = None
    cutoff_datetime: Optional[datetime] = None
    total_cost: Optional[Decimal] = None
    currency: Optional[str] = None
    capacity_constraints: Optional[str] = None
    notes: Optional[str] = None
    consolidation_metadata: Optional[str] = None


class ShippingRouteConsolidationPublic(ShippingRouteConsolidationBase, BasePublic):
    id: uuid.UUID


class ShippingOrderConsolidationBase(Base):
    """
    Lien Commande â†” Consolidation (quantitÃ©s/poids/volume + prix acceptÃ©).
    Sert d'ancrage pour le suivi et l'audit de tarification.
    """
    
    consolidation_id: uuid.UUID = Field(foreign_key="shipping_route_consolidations.id", description="Consolidation parente")
    order_id: uuid.UUID = Field(description="ID de la commande")
    
    # QuantitÃ©s physiques
    package_qty: int = Field(default=1, description="Nombre de colis")
    weight_kg: Optional[float] = Field(default=None, description="Poids en kg")
    volume_m3: Optional[float] = Field(default=None, description="Volume en mÂ³")
    
    # Dimensions si colis unique
    length_m: Optional[float] = Field(default=None, description="Longueur en m")
    width_m: Optional[float] = Field(default=None, description="Largeur en m") 
    height_m: Optional[float] = Field(default=None, description="Hauteur en m")
    
    # Prix acceptÃ© lors du choix par le client (remplace RateQuote)
    agreed_shipping_price: Optional[Decimal] = Field(default=None, sa_column=Column(NUMERIC(12, 2)), description="Prix acceptÃ©")
    agreed_currency: Optional[str] = Field(default="EUR", max_length=3, description="Devise acceptÃ©e")
    
    # MÃ©tadonnÃ©es de la rÃ©servation
    reserved_at: datetime = Field(default_factory=datetime.utcnow, description="Date de rÃ©servation")
    confirmed_at: Optional[datetime] = Field(default=None, description="Date de confirmation")
    
    # ClÃ© d'idempotence pour Ã©viter les doublons
    idempotency_key: Optional[str] = Field(default=None, max_length=100, description="ClÃ© d'idempotence")
    
    # Statut de cette liaison
    status_code: Optional[str] = Field(default="reserved", max_length=50, description="Statut de la liaison")
    
    # Notes
    notes: Optional[str] = Field(default=None, max_length=500, description="Notes spÃ©cifiques")


class ShippingOrderConsolidation(ShippingOrderConsolidationBase, table=True):
    """Lien Commande â†” Consolidation"""
    __tablename__ = "shipping_order_consolidations"
    
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True)
    )
    
    # Relations
    consolidation: ShippingRouteConsolidation = Relationship(
        back_populates="order_links",
        sa_relationship_kwargs={"lazy": "selectin"}
    )


class ShippingOrderConsolidationCreate(ShippingOrderConsolidationBase, BaseCreate):
    pass


class ShippingOrderConsolidationUpdate(ShippingOrderConsolidationBase, BaseUpdate):
    package_qty: Optional[int] = None
    weight_kg: Optional[float] = None
    volume_m3: Optional[float] = None
    length_m: Optional[float] = None
    width_m: Optional[float] = None
    height_m: Optional[float] = None
    agreed_shipping_price: Optional[Decimal] = None
    agreed_currency: Optional[str] = None
    confirmed_at: Optional[datetime] = None
    status_code: Optional[str] = None
    notes: Optional[str] = None


class ShippingOrderConsolidationPublic(ShippingOrderConsolidationBase, BasePublic):
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
    
    consolidation_id: uuid.UUID = Field(foreign_key="shipping_route_consolidations.id", description="Consolidation")
    route_step_id: uuid.UUID = Field(foreign_key="shipping_route_steps.id", description="Ã‰tape de route")
    order_id: uuid.UUID = Field(description="ID de la commande")
    
    # Statut pour cette Ã©tape spÃ©cifique
    status_code: Optional[str] = Field(default="pending", max_length=50, description="Statut de l'Ã©tape")
    is_done: bool = Field(default=False, description="Ã‰tape terminÃ©e")
    
    # Suivi
    scan_ref: Optional[str] = Field(default=None, max_length=100, description="RÃ©fÃ©rence de scan")
    tracking_number: Optional[str] = Field(default=None, max_length=100, description="NumÃ©ro de suivi transporteur")
    
    # Timeline
    occurred_at: Optional[datetime] = Field(default=None, description="Quand l'Ã©vÃ©nement s'est produit")
    last_event_at: Optional[datetime] = Field(default=None, description="Dernier Ã©vÃ©nement enregistrÃ©")
    
    # Preuves
    evidence_url: Optional[str] = Field(default=None, max_length=500, description="URL de preuve")
    signature_name: Optional[str] = Field(default=None, max_length=100, description="Nom du signataire")
    actor: Optional[str] = Field(default=None, max_length=100, description="Acteur ayant effectuÃ© l'action")
    
    # Notes
    notes: Optional[str] = Field(default=None, max_length=500, description="Notes spÃ©cifiques Ã  cette Ã©tape")


class ShippingOrderStepConsolidation(ShippingOrderStepConsolidationBase, table=True):
    """Suivi d'une commande pour une Ã©tape donnÃ©e"""
    __tablename__ = "shipping_order_step_consolidations"
    
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True)
    )


class ShippingOrderStepConsolidationCreate(ShippingOrderStepConsolidationBase, BaseCreate):
    pass


class ShippingOrderStepConsolidationUpdate(ShippingOrderStepConsolidationBase, BaseUpdate):
    status_code: Optional[str] = None
    is_done: Optional[bool] = None
    scan_ref: Optional[str] = None
    tracking_number: Optional[str] = None
    occurred_at: Optional[datetime] = None
    last_event_at: Optional[datetime] = None
    evidence_url: Optional[str] = None
    signature_name: Optional[str] = None
    actor: Optional[str] = None
    notes: Optional[str] = None


class ShippingOrderStepConsolidationPublic(ShippingOrderStepConsolidationBase, BasePublic):
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