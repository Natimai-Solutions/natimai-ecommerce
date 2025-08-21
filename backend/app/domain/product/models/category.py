import uuid

from sqlmodel import Field, SQLModel

from app.domain.base_models import Base, BaseCreate, BaseUpdate, BasePublic


class CategoryBase(Base):
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


class CategoryCreate(CategoryBase, BaseCreate):
    pass


class CategoryUpdate(CategoryBase, BaseUpdate):
    name: str | None = None
    description: str | None = None


class Category(CategoryBase, Base, table=True):
    __tablename__ = "categories"
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        description="Unique identifier for the category",
    )


class CategoryPublic(CategoryBase, BasePublic):
    id: uuid.UUID


class CategoriesPublic(SQLModel):
    categories: list[CategoryPublic] = Field(
        default_factory=list,
        description="List of categories",
    )
