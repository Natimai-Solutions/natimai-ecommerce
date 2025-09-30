"""
Modèles de référentiels pour le système de livraison.
Acteurs métier et lieux physiques.
"""

import uuid
from typing import Optional, List, TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate

if TYPE_CHECKING:
    from app.features.shipping.models.shipping_route import ShippingRoute


class PartnerBase(Base):
    """Acteur métier (client ou fournisseur)"""
    name: str = Field(max_length=200, description="Nom de l'acteur")
    phone: Optional[str] = Field(default=None, max_length=50, description="Téléphone")
    email: Optional[str] = Field(default=None, max_length=100, description="Email")
    
    # Adresse
    address_line1: Optional[str] = Field(default=None, max_length=200)
    address_line2: Optional[str] = Field(default=None, max_length=200)
    city: Optional[str] = Field(default=None, max_length=100)
    postal_code: Optional[str] = Field(default=None, max_length=20)
    country: Optional[str] = Field(default=None, max_length=2, description="Code pays ISO")


class Partner(PartnerBase, table=True):
    """Acteur métier (client ou fournisseur)"""
    __tablename__ = "partners"
    
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True)
    )
    
    # Relations
    origin_routes: List["ShippingRoute"] = Relationship(
        back_populates="from_partner",
        sa_relationship_kwargs={"foreign_keys": "[ShippingRoute.from_partner_id]"}
    )
    destination_routes: List["ShippingRoute"] = Relationship(
        back_populates="to_partner", 
        sa_relationship_kwargs={"foreign_keys": "[ShippingRoute.to_partner_id]"}
    )


class PartnerCreate(PartnerBase, BaseCreate):
    pass


class PartnerUpdate(PartnerBase, BaseUpdate):
    name: Optional[str] = None
    is_customer: Optional[bool] = None
    is_supplier: Optional[bool] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None


class PartnerPublic(PartnerBase, BasePublic):
    id: uuid.UUID


class PartnersPublic(SQLModel):
    data: list[PartnerPublic] = Field(
        default_factory=list,
        description="List of partners",
    )
    count: int = Field(
        default=0,
        description="Total number of partners",
    )