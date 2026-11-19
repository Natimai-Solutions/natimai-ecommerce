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
    #: Path of the brand page (``/marque/<slug>``), unique (lot BR).
    slug: str | None = Field(default=None, max_length=120, unique=True, index=True)
    #: Logo from the media library (WebP widths, srcset).
    media_id: uuid.UUID | None = Field(
        default=None, foreign_key="media_assets.id", ondelete="SET NULL"
    )
    #: Created from a supplier's manufacturer name: shown (facet, brand page)
    #: once the admin has checked it.
    is_validated: bool = Field(
        default=True, sa_column_kwargs={"server_default": "true"}
    )


class BrandCreate(BrandBase, BaseCreate):
    """Represents brand create."""

    pass


class BrandUpdate(BrandBase, BaseUpdate):
    """Represents brand update."""

    name: str | None = None
    description: str | None = None
    image_url: str | None = None
    slug: str | None = None
    media_id: uuid.UUID | None = None
    is_validated: bool | None = None


class Brand(BrandBase, table=True):
    """Represents brand."""

    __tablename__ = "brands"
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        description="Unique identifier for the brand",
    )


class BrandAlias(SQLModel, table=True):
    """Another spelling of a brand (« HP Inc. », « Hewlett-Packard » → HP),
    stored by its normalized key."""

    __tablename__ = "brand_aliases"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    brand_id: uuid.UUID = Field(foreign_key="brands.id", index=True, ondelete="CASCADE")
    alias: str = Field(max_length=100)
    key: str = Field(max_length=100, unique=True, index=True)


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
