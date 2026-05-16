# mypy: disable-error-code="assignment,misc,override"

import uuid

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


class CategoryCreate(CategoryBase, BaseCreate):
    """Represents category create."""

    pass


class CategoryUpdate(CategoryBase, BaseUpdate):
    """Represents category update."""

    pass


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
