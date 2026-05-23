# mypy: disable-error-code="assignment,misc,override"

import uuid

from sqlmodel import Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class BrandBase(Base):
    """Represents brand base."""

    name: str = Field(
        description="Name of the brand",
        max_length=100,
        index=True,
    )
    description: str | None = Field(
        default=None,
        max_length=500,
        description="Description of the brand",
    )
    image_url: str | None = Field(
        default=None,
        max_length=500,
        description="URL of the brand image",
    )


class BrandCreate(BrandBase, BaseCreate):
    """Represents brand create."""

    pass


class BrandUpdate(BrandBase, BaseUpdate):
    """Represents brand update."""

    name: str | None = None
    description: str | None = None
    image_url: str | None = None


class Brand(BrandBase, table=True):
    """Represents brand."""

    __tablename__ = "brands"
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        description="Unique identifier for the brand",
    )


class BrandPublic(BrandBase, BasePublic):
    """Represents brand public."""

    id: uuid.UUID


class BrandsPublic(SQLModel):
    """Represents brands public."""

    data: list[BrandPublic] = Field(
        default_factory=list,
        description="List of brands",
    )
    count: int = Field(
        default=0,
        description="Total number of brands",
    )
