# mypy: disable-error-code="assignment,misc,override"

import uuid
from decimal import Decimal

from sqlmodel import Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class CategoryBase(Base):
    """Represents category base."""

    name: str = Field(
        index=True,
        max_length=100,
        description="Name of the category",
    )
    description: str | None = Field(
        default=None,
        max_length=500,
        description="Description of the category",
    )
    image_url: str | None = Field(
        default=None,
        max_length=500,
        description="URL of the category image",
    )
    default_tax_rate_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="tax_rates.id",
        index=True,
        description="Default tax rate applied to products in this category",
    )
    default_customs_rate_pct: Decimal | None = Field(
        default=None,
        ge=0,
        decimal_places=2,
        description=(
            "Default customs rate percentage for products in this category "
            "(used when Product.customs_rate_pct is not set)"
        ),
    )


class CategoryCreate(CategoryBase, BaseCreate):
    """Represents category create."""

    pass


class CategoryUpdate(CategoryBase, BaseUpdate):
    """Represents category update."""

    default_tax_rate_id: uuid.UUID | None = None


class Category(CategoryBase, table=True):
    """Represents category."""

    __tablename__ = "categories"
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        description="Unique identifier for the category",
    )


class CategoryPublic(CategoryBase, BasePublic):
    """Represents category public."""

    id: uuid.UUID


class CategoriesPublic(SQLModel):
    """Represents categories public."""

    data: list[CategoryPublic] = Field(
        default_factory=list,
        description="List of categories",
    )
    count: int = Field(
        default=0,
        description="Total number of categories",
    )
