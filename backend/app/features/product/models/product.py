# mypy: disable-error-code="assignment,misc,override"

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlmodel import Field, Relationship, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate
from app.features.product.models.category import Category


class SupplierType(str, Enum):
    """Supported product suppliers/vendors"""

    INGRAM_MICRO = "ingram_micro"
    TECH_DATA = "tech_data"
    SYNNEX = "synnex"
    ARROW = "arrow"
    AVNET = "avnet"
    LOCAL = "local"  # For locally managed products


class ProductBase(Base):
    """Represents product base."""

    name: str = Field(
        description="Name of the product",
        max_length=100,
    )
    description: str | None = Field(
        default=None,
        max_length=500,
        description="Description of the product",
    )
    long_description: str | None = Field(
        default=None,
        description="Long description of the product",
    )
    base_price: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        decimal_places=2,
        description="Base price of the product (can be 0 for products without pricing)",
    )
    has_variants: bool = Field(
        default=False,
        description="Indicates if the product has variants",
    )

    # Generic supplier/vendor integration fields
    supplier_sku: str | None = Field(
        default=None,
        max_length=50,
        index=True,
        description="Supplier/vendor SKU identifier",
    )
    vendor_part_number: str | None = Field(
        default=None,
        max_length=100,
        description="Manufacturer part number",
    )
    manufacturer: str | None = Field(
        default=None,
        max_length=100,
        description="Product manufacturer",
    )
    supplier_name: str | None = Field(
        default=None,
        max_length=100,
        index=True,
        description="Name of the supplier/vendor (Ingram Micro, Tech Data, etc.)",
    )
    supplier_category: str | None = Field(
        default=None,
        max_length=50,
        description="Supplier's product category",
    )
    supplier_subcategory: str | None = Field(
        default=None,
        max_length=50,
        description="Supplier's product subcategory",
    )
    weight: float | None = Field(
        default=None,
        ge=0,
        description="Product weight in kg",
    )
    dimensions_length: float | None = Field(
        default=None,
        ge=0,
        description="Product length in cm",
    )
    dimensions_width: float | None = Field(
        default=None,
        ge=0,
        description="Product width in cm",
    )
    dimensions_height: float | None = Field(
        default=None,
        ge=0,
        description="Product height in cm",
    )
    supplier_image_url: str | None = Field(
        default=None,
        max_length=500,
        description="Product image URL from supplier",
    )
    supplier_spec_url: str | None = Field(
        default=None,
        max_length=500,
        description="Product specification URL from supplier",
    )
    supplier_quantity: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        decimal_places=2,
        description="Available quantity from supplier",
    )
    supplier_price: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        decimal_places=2,
        description="Price from supplier",
    )
    supplier_price_currency: str | None = Field(
        default=None,
        max_length=10,
        description="Currency of the supplier price (e.g., USD, EUR)",
    )
    last_supplier_sync: datetime | None = Field(
        default=None,
        description="Last synchronization timestamp with supplier",
    )
    is_supplier_managed: bool = Field(
        default=False,
        description="Indicates if this product is managed by a supplier",
    )
    last_enrichment_sync: datetime | None = Field(
        default=None,
        description="Last synchronization timestamp for enrichment data",
    )
    is_enriched: bool = Field(
        default=False,
        description="Indicates if the product has been enriched with external data",
    )
    enrichment_supplier_id: str | None = Field(
        default=None,
        description="Identifier of the enrichment data supplier",
    )
    upc: str | None = Field(
        default=None,
        max_length=50,
        description="Universal Product Code (UPC) of the product",
    )
    ean: str | None = Field(
        default=None,
        max_length=50,
        description="European Article Number (EAN) of the product",
    )
    image_url: str | None = Field(
        default=None,
        max_length=500,
        description="Main image URL of the product",
    )
    release_date: str | None = Field(
        default=None, description="Release date of the product"
    )
    end_of_life_date: str | None = Field(
        default=None, description="End of life date of the product"
    )


class ProductCreate(ProductBase, BaseCreate):
    """Represents product create."""

    pass


class ProductUpdate(ProductBase, BaseUpdate):
    """Represents product update."""

    name: str | None = None
    description: str | None = None
    base_price: Decimal | None = None
    has_variants: bool | None = None

    # Generic supplier fields (optional for updates)
    supplier_sku: str | None = None
    vendor_part_number: str | None = None
    manufacturer: str | None = None
    supplier_name: str | None = None
    supplier_category: str | None = None
    supplier_subcategory: str | None = None
    weight: float | None = None
    dimensions_length: float | None = None
    dimensions_width: float | None = None
    dimensions_height: float | None = None
    supplier_image_url: str | None = None
    supplier_spec_url: str | None = None
    last_supplier_sync: datetime | None = None
    is_supplier_managed: bool | None = None


class Product(ProductBase, table=True):
    """Represents product."""

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
        index=True,
        description="Category ID of the product",
    )
    category: Category | None = Relationship(
        sa_relationship_kwargs={
            "foreign_keys": "[Product.category_id]",
            "lazy": "selectin",
        },
    )


class ProductPublic(ProductBase, BasePublic):
    """Represents product public."""

    id: uuid.UUID
    category_id: uuid.UUID | None = None

    # Generic supplier fields (exposed in public API)
    supplier_sku: str | None = None
    vendor_part_number: str | None = None
    manufacturer: str | None = None
    supplier_name: str | None = None
    supplier_category: str | None = None
    supplier_subcategory: str | None = None
    weight: float | None = None
    dimensions_length: float | None = None
    dimensions_width: float | None = None
    dimensions_height: float | None = None
    supplier_image_url: str | None = None
    supplier_spec_url: str | None = None
    last_supplier_sync: datetime | None = None
    is_supplier_managed: bool = False


class ProductsPublic(SQLModel):
    """Represents products public."""

    data: list[ProductPublic] = Field(
        default_factory=list,
        description="List of products",
    )
    count: int = Field(
        default=0,
        description="Total number of products",
    )
