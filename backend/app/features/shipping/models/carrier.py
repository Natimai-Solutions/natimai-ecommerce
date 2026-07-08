"""Shipping carriers (La Poste / OPT, DHL, …).

A carrier optionally carries a tracking-URL template with a ``{ref}`` placeholder
(e.g. ``https://www.dhl.com/track?id={ref}``) so the storefront can build a
clickable tracking link from a parcel's ``tracking_ref``.
"""

# mypy: disable-error-code="assignment,misc,override"

import uuid

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class CarrierBase(Base):
    """Represents a shipping carrier."""

    name: str = Field(max_length=100, description="Display name, e.g. 'DHL'")
    code: str = Field(max_length=50, index=True, description="Unique slug, e.g. 'dhl'")
    tracking_url_template: str | None = Field(
        default=None,
        max_length=500,
        description="Tracking URL with a {ref} placeholder (https only).",
    )


class Carrier(CarrierBase, table=True):
    """Represents a shipping carrier."""

    __tablename__ = "carriers"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True),
    )


class CarrierCreate(CarrierBase, BaseCreate):
    """Represents carrier create."""

    pass


class CarrierUpdate(BaseUpdate):
    """Represents carrier update."""

    name: str | None = None
    code: str | None = None
    tracking_url_template: str | None = None


class CarrierPublic(CarrierBase, BasePublic):
    """Represents carrier public."""

    id: uuid.UUID


class CarriersPublic(SQLModel):
    """Paginated carrier list."""

    data: list[CarrierPublic] = Field(default_factory=list)
    count: int = Field(default=0)
