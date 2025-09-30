"""
ModÃ¨les de tÃ¢ches de livraison et packages.
Dernier kilomÃ¨tre et gestion des colis.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, Relationship, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate

if TYPE_CHECKING:
    from app.features.shipping.models.place import Place


class DeliveryTaskBase(Base):
    """
    Ordre de livraison dernier kilomÃ¨tre (domicile ou retrait Ã  l'entrepÃ´t Place).
    IndÃ©pendant des consolidations amont.
    """

    order_id: uuid.UUID = Field(description="ID de la commande Ã  livrer")
    address_place_id: uuid.UUID = Field(
        foreign_key="places.id",
        description="Delivery place (domicile ou point de retrait)",
    )

    # Delivery type
    delivery_type: str = Field(
        max_length=50, description="Type: home_delivery, pickup_point, warehouse_pickup"
    )

    # FenÃªtre de livraison
    window_start: datetime | None = Field(
        default=None, description="DÃ©but de fenÃªtre de livraison"
    )
    window_end: datetime | None = Field(
        default=None, description="Fin de fenÃªtre de livraison"
    )

    # Assignation
    assignee: str | None = Field(
        default=None, max_length=100, description="Livreur assignÃ©"
    )
    delivery_service: str | None = Field(
        default=None, max_length=100, description="Service de livraison"
    )

    # Statut
    status_code: str | None = Field(
        default="pending", max_length=50, description="Statut de la tÃ¢che"
    )

    # Instructions spÃ©ciales
    delivery_instructions: str | None = Field(
        default=None, max_length=500, description="Delivery instructions"
    )
    access_code: str | None = Field(
        default=None, max_length=50, description="Code d'accÃ¨s"
    )

    # Horaires prÃ©fÃ©rÃ©s
    preferred_time_slot: str | None = Field(
        default=None, max_length=50, description="CrÃ©neau prÃ©fÃ©rÃ©"
    )

    # Preuves de livraison
    proof_url: str | None = Field(
        default=None, max_length=500, description="URL de preuve de livraison"
    )
    signature_name: str | None = Field(
        default=None, max_length=100, description="Nom du signataire"
    )
    photo_url: str | None = Field(
        default=None, max_length=500, description="Photo de la livraison"
    )

    # Timeline
    scheduled_at: datetime | None = Field(
        default=None, description="Livraison programmÃ©e"
    )
    attempted_at: datetime | None = Field(
        default=None, description="Tentative de livraison"
    )
    delivered_at: datetime | None = Field(
        default=None, description="Livraison effectuÃ©e"
    )

    # Notes
    notes: str | None = Field(
        default=None, max_length=500, description="Notes libres"
    )


class DeliveryTask(DeliveryTaskBase, table=True):
    """Ordre de livraison dernier kilomÃ¨tre"""

    __tablename__ = "delivery_tasks"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True),
    )

    # Relations
    address_place: "Place" = Relationship(
        back_populates="delivery_tasks", sa_relationship_kwargs={"lazy": "selectin"}
    )


class DeliveryTaskCreate(DeliveryTaskBase, BaseCreate):
    pass


class DeliveryTaskUpdate(DeliveryTaskBase, BaseUpdate):
    address_place_id: uuid.UUID | None = None
    delivery_type: str | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    assignee: str | None = None
    delivery_service: str | None = None
    status_code: str | None = None
    delivery_instructions: str | None = None
    access_code: str | None = None
    preferred_time_slot: str | None = None
    proof_url: str | None = None
    signature_name: str | None = None
    photo_url: str | None = None
    scheduled_at: datetime | None = None
    attempted_at: datetime | None = None
    delivered_at: datetime | None = None
    notes: str | None = None


class DeliveryTaskPublic(DeliveryTaskBase, BasePublic):
    id: uuid.UUID


class PackageBase(Base):
    """Si une commande est expÃ©diÃ©e en plusieurs colis unitaires"""

    order_id: uuid.UUID = Field(description="ID de la commande")

    # Identification du colis
    package_code: str | None = Field(
        default=None, max_length=100, description="Code du colis"
    )
    tracking_number: str | None = Field(
        default=None, max_length=100, description="NumÃ©ro de suivi"
    )

    # CaractÃ©ristiques physiques
    weight_kg: float | None = Field(default=None, description="Weight in kg")
    length_m: float | None = Field(default=None, description="Length in m")
    width_m: float | None = Field(default=None, description="Width in m")
    height_m: float | None = Field(default=None, description="Height in m")
    volume_m3: float | None = Field(
        default=None, description="Volume calculÃ© en mÂ³"
    )

    # Contraintes spÃ©ciales
    is_fragile: bool = Field(default=False, description="Fragile")
    is_hazmat: bool = Field(default=False, description="MatiÃ¨res dangereuses")
    requires_temperature_control: bool = Field(
        default=False, description="ContrÃ´le tempÃ©rature"
    )

    # TempÃ©rature si nÃ©cessaire
    min_temperature_c: float | None = Field(
        default=None, description="TempÃ©rature min Â°C"
    )
    max_temperature_c: float | None = Field(
        default=None, description="TempÃ©rature max Â°C"
    )

    # Valeur dÃ©clarÃ©e
    declared_value: float | None = Field(
        default=None, description="Valeur dÃ©clarÃ©e"
    )
    currency: str | None = Field(default="EUR", max_length=3, description="Currency")

    # Package status
    status_code: str | None = Field(
        default="prepared", max_length=50, description="Package status"
    )

    # Notes
    contents_description: str | None = Field(
        default=None, max_length=500, description="Description du contenu"
    )
    handling_notes: str | None = Field(
        default=None, max_length=500, description="Notes de manipulation"
    )


class Package(PackageBase, table=True):
    """Si une commande est expÃ©diÃ©e en plusieurs colis unitaires"""

    __tablename__ = "packages"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True),
    )


class PackageCreate(PackageBase, BaseCreate):
    pass


class PackageUpdate(PackageBase, BaseUpdate):
    package_code: str | None = None
    tracking_number: str | None = None
    weight_kg: float | None = None
    length_m: float | None = None
    width_m: float | None = None
    height_m: float | None = None
    volume_m3: float | None = None
    is_fragile: bool | None = None
    is_hazmat: bool | None = None
    requires_temperature_control: bool | None = None
    min_temperature_c: float | None = None
    max_temperature_c: float | None = None
    declared_value: float | None = None
    currency: str | None = None
    status_code: str | None = None
    contents_description: str | None = None
    handling_notes: str | None = None


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
