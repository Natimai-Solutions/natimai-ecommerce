import uuid

from sqlmodel import Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class ProductVariantBase(Base):
    name: str = Field(
        description="Name of the product variant",
        max_length=100,
    )
    description: str | None = Field(
        default=None,
        max_length=500,
        description="Description of the product variant",
    )
    price: float = Field(
        gt=0,
        description="Price of the product variant",
    )


class ProductVariantCreate(ProductVariantBase, BaseCreate):
    pass


class ProductVariantUpdate(ProductVariantBase, BaseUpdate):
    name: str | None = None
    description: str | None = None
    price: float | None = None


class ProductVariant(ProductVariantBase, Base, table=True):
    __tablename__ = "product_variants"
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        description="Unique identifier for the product variant",
    )
    product_id: uuid.UUID = Field(
        foreign_key="products.id",
        description="Product ID of the product variant",
    )
    inventory_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="inventories.id",
        description="Inventory ID for this variant",
    )


class ProductVariantPublic(ProductVariantBase, BasePublic):
    id: uuid.UUID
    product_id: uuid.UUID
    inventory_id: uuid.UUID | None


class ProductVariantsPublic(SQLModel):
    product_variants: list[ProductVariantPublic] = Field(
        default_factory=list,
        description="List of product variants",
    )
