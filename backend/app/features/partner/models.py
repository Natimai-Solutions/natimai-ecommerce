"""
Reference models for the delivery system.
Business actors and physical places.
"""

# mypy: disable-error-code="assignment,misc,override"

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate

if TYPE_CHECKING:
    pass


class PartnerBase(Base):
    """Business actor (customer or supplier)"""

    name: str = Field(max_length=200, description="Nom de l'acteur")
    phone: str | None = Field(default=None, max_length=50, description="Phone")
    email: str | None = Field(
        default=None,
        max_length=100,
        index=True,
        description="Email",
    )

    # Adresse
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
    is_supplier: bool = Field(default=False, description="Is a supplier")


class PartnerCreate(PartnerBase, BaseCreate):
    """Represents partner create."""

    pass


class PartnerUpdate(PartnerBase, BaseUpdate):
    """Represents partner update."""

    name: str | None = None
    is_customer: bool | None = None
    is_supplier: bool | None = None
    phone: str | None = None
    email: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    postal_code: str | None = None
    country: str | None = None


class Partner(PartnerBase, table=True):
    """Represents partner."""

    __tablename__ = "partners"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True),
    )


class PartnerPublic(PartnerBase, BasePublic):
    """Represents partner public."""

    id: uuid.UUID


class PartnersPublic(SQLModel):
    """Represents partners public."""

    data: list[PartnerPublic] = Field(
        default_factory=list,
        description="List of partners",
    )
    count: int = Field(
        default=0,
        description="Total number of partners",
    )
