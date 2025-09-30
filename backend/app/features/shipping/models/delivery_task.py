"""
ModÃ¨les de tÃ¢ches de livraison et packages.
Dernier kilomÃ¨tre et gestion des colis.
"""

import uuid
from typing import Optional, TYPE_CHECKING
from datetime import datetime

from sqlmodel import Field, Relationship, SQLModel
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate

if TYPE_CHECKING:
    from app.features.shipping.models.place import Place


class DeliveryTaskBase(Base):
    """
    Ordre de livraison dernier kilomÃ¨tre (domicile ou retrait Ã  l'entrepÃ´t Place).
    IndÃ©pendant des consolidations amont.
    """
    
    order_id: uuid.UUID = Field(description="ID de la commande Ã  livrer")
    address_place_id: uuid.UUID = Field(foreign_key="places.id", description="Lieu de livraison (domicile ou point de retrait)")
    
    # Type de livraison
    delivery_type: str = Field(max_length=50, description="Type: home_delivery, pickup_point, warehouse_pickup")
    
    # FenÃªtre de livraison
    window_start: Optional[datetime] = Field(default=None, description="DÃ©but de fenÃªtre de livraison")
    window_end: Optional[datetime] = Field(default=None, description="Fin de fenÃªtre de livraison")
    
    # Assignation
    assignee: Optional[str] = Field(default=None, max_length=100, description="Livreur assignÃ©")
    delivery_service: Optional[str] = Field(default=None, max_length=100, description="Service de livraison")
    
    # Statut
    status_code: Optional[str] = Field(default="pending", max_length=50, description="Statut de la tÃ¢che")
    
    # Instructions spÃ©ciales
    delivery_instructions: Optional[str] = Field(default=None, max_length=500, description="Instructions de livraison")
    access_code: Optional[str] = Field(default=None, max_length=50, description="Code d'accÃ¨s")
    
    # Horaires prÃ©fÃ©rÃ©s
    preferred_time_slot: Optional[str] = Field(default=None, max_length=50, description="CrÃ©neau prÃ©fÃ©rÃ©")
    
    # Preuves de livraison
    proof_url: Optional[str] = Field(default=None, max_length=500, description="URL de preuve de livraison")
    signature_name: Optional[str] = Field(default=None, max_length=100, description="Nom du signataire")
    photo_url: Optional[str] = Field(default=None, max_length=500, description="Photo de la livraison")
    
    # Timeline
    scheduled_at: Optional[datetime] = Field(default=None, description="Livraison programmÃ©e")
    attempted_at: Optional[datetime] = Field(default=None, description="Tentative de livraison")
    delivered_at: Optional[datetime] = Field(default=None, description="Livraison effectuÃ©e")
    
    # Notes
    notes: Optional[str] = Field(default=None, max_length=500, description="Notes libres")


class DeliveryTask(DeliveryTaskBase, table=True):
    """Ordre de livraison dernier kilomÃ¨tre"""
    __tablename__ = "delivery_tasks"
    
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True)
    )
    
    # Relations
    address_place: "Place" = Relationship(
        back_populates="delivery_tasks",
        sa_relationship_kwargs={"lazy": "selectin"}
    )


class DeliveryTaskCreate(DeliveryTaskBase, BaseCreate):
    pass


class DeliveryTaskUpdate(DeliveryTaskBase, BaseUpdate):
    address_place_id: Optional[uuid.UUID] = None
    delivery_type: Optional[str] = None
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None
    assignee: Optional[str] = None
    delivery_service: Optional[str] = None
    status_code: Optional[str] = None
    delivery_instructions: Optional[str] = None
    access_code: Optional[str] = None
    preferred_time_slot: Optional[str] = None
    proof_url: Optional[str] = None
    signature_name: Optional[str] = None
    photo_url: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    attempted_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    notes: Optional[str] = None


class DeliveryTaskPublic(DeliveryTaskBase, BasePublic):
    id: uuid.UUID


class PackageBase(Base):
    """Si une commande est expÃ©diÃ©e en plusieurs colis unitaires"""
    
    order_id: uuid.UUID = Field(description="ID de la commande")
    
    # Identification du colis
    package_code: Optional[str] = Field(default=None, max_length=100, description="Code du colis")
    tracking_number: Optional[str] = Field(default=None, max_length=100, description="NumÃ©ro de suivi")
    
    # CaractÃ©ristiques physiques
    weight_kg: Optional[float] = Field(default=None, description="Poids en kg")
    length_m: Optional[float] = Field(default=None, description="Longueur en m")
    width_m: Optional[float] = Field(default=None, description="Largeur en m")
    height_m: Optional[float] = Field(default=None, description="Hauteur en m")
    volume_m3: Optional[float] = Field(default=None, description="Volume calculÃ© en mÂ³")
    
    # Contraintes spÃ©ciales
    is_fragile: bool = Field(default=False, description="Fragile")
    is_hazmat: bool = Field(default=False, description="MatiÃ¨res dangereuses")
    requires_temperature_control: bool = Field(default=False, description="ContrÃ´le tempÃ©rature")
    
    # TempÃ©rature si nÃ©cessaire
    min_temperature_c: Optional[float] = Field(default=None, description="TempÃ©rature min Â°C")
    max_temperature_c: Optional[float] = Field(default=None, description="TempÃ©rature max Â°C")
    
    # Valeur dÃ©clarÃ©e
    declared_value: Optional[float] = Field(default=None, description="Valeur dÃ©clarÃ©e")
    currency: Optional[str] = Field(default="EUR", max_length=3, description="Devise")
    
    # Statut du colis
    status_code: Optional[str] = Field(default="prepared", max_length=50, description="Statut du colis")
    
    # Notes
    contents_description: Optional[str] = Field(default=None, max_length=500, description="Description du contenu")
    handling_notes: Optional[str] = Field(default=None, max_length=500, description="Notes de manipulation")


class Package(PackageBase, table=True):
    """Si une commande est expÃ©diÃ©e en plusieurs colis unitaires"""
    __tablename__ = "packages"
    
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True)
    )


class PackageCreate(PackageBase, BaseCreate):
    pass


class PackageUpdate(PackageBase, BaseUpdate):
    package_code: Optional[str] = None
    tracking_number: Optional[str] = None
    weight_kg: Optional[float] = None
    length_m: Optional[float] = None
    width_m: Optional[float] = None
    height_m: Optional[float] = None
    volume_m3: Optional[float] = None
    is_fragile: Optional[bool] = None
    is_hazmat: Optional[bool] = None
    requires_temperature_control: Optional[bool] = None
    min_temperature_c: Optional[float] = None
    max_temperature_c: Optional[float] = None
    declared_value: Optional[float] = None
    currency: Optional[str] = None
    status_code: Optional[str] = None
    contents_description: Optional[str] = None
    handling_notes: Optional[str] = None


class PackagePublic(PackageBase, BasePublic):
    id: uuid.UUID


class DeliveryTasksPublic(SQLModel):
    data: list[DeliveryTaskPublic] = Field(
        default_factory=list,
        description="List of delivery tasks",
    )
    count: int = Field(
        default=0,
        description="Total number of delivery tasks",
    )


class PackagesPublic(SQLModel):
    data: list[PackagePublic] = Field(
        default_factory=list,
        description="List of packages",
    )
    count: int = Field(
        default=0,
        description="Total number of packages",
    )

class DeliveryTasksPublic(SQLModel):
    data: list[DeliveryTaskPublic] = Field(
        default_factory=list,
        description="List of delivery tasks",
    )
    count: int = Field(
        default=0,
        description="Total number of delivery tasks",
    )


class PackagesPublic(SQLModel):
    data: list[PackagePublic] = Field(
        default_factory=list,
        description="List of packages",
    )
    count: int = Field(
        default=0,
        description="Total number of packages",
    )
