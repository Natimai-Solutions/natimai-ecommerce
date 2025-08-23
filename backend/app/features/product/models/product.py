import uuid

from sqlmodel import Field, SQLModel, Relationship
from app.features.base.models import Base, BaseCreate, BaseUpdate, BasePublic


class ProductBase(Base):
    name: str = Field(
        description="Name of the product",
        max_length=100,
    )
    description: str | None = Field(
        default=None,
        max_length=500,
        description="Description of the product",
    )
    base_price: float = Field(
        gt=0,
        description="Base price of the product",
    )
    has_variants: bool = Field(
        default=False,
        description="Indicates if the product has variants",
    )


class ProductCreate(ProductBase, BaseCreate):
    pass


class ProductUpdate(ProductBase, BaseUpdate):
    name: str | None = None
    description: str | None = None
    base_price: float | None = None
    has_variants: bool | None = None


class Product(ProductBase, Base, table=True):
    __tablename__ = "products"
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        description="Unique identifier for the product",
    )
    category_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="categories.id",
        description="Category ID of the product",
    )
    total_stock_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="inventories.id",
        description="Total stock ID of the product, including all variants",
    )


class ProductPublic(ProductBase, BasePublic):
    id: uuid.UUID
    category_id: uuid.UUID | None = None


class ProductsPublic(SQLModel):
    products: list[ProductPublic] = Field(
        default_factory=list,
        description="List of products",
    )
    total_count: int = Field(
        default=0,
        description="Total number of products",
    )
