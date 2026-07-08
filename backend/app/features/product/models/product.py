# mypy: disable-error-code="assignment,misc,override"

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import JSON, Column
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
    cost_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        decimal_places=2,
        description="Product cost amount used to compute selling price",
    )
    cost_currency: str = Field(
        default="XPF",
        max_length=10,
        description="Currency of the product cost amount",
    )
    customs_rate_pct: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        decimal_places=2,
        description="Customs rate percentage applied before margin",
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
    supplier_place_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="places.id",
        index=True,
        description="Origin place when supplier-sourced (drives the first leg)",
    )
    overridden_fields: list[str] | None = Field(
        default=None,
        sa_column=Column(JSON),
        description=(
            "Field names manually set by an admin. The supplier sync must not "
            "overwrite these — they are the admin's authoritative values."
        ),
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
    tax_rate_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="tax_rates.id",
        index=True,
        description="Tax rate applied to this product",
    )
    is_featured: bool = Field(
        default=False,
        description="Whether the product is highlighted in featured listings",
    )
    featured_position: int | None = Field(
        default=None,
        ge=0,
        description="Optional ordering position for featured listings",
    )
    featured_until: datetime | None = Field(
        default=None,
        description="Optional expiration date for featured visibility",
    )
    technical_specifications: list[dict[str, Any]] | None = Field(
        default=None,
        sa_column=Column(JSON),
        description="Technical specifications extracted from Icecat",
    )
    features: list[str] | None = Field(
        default=None,
        sa_column=Column(JSON),
        description="Feature bullet points extracted from Icecat",
    )
    icecat_images: list[dict[str, Any]] | None = Field(
        default=None,
        sa_column=Column(JSON),
        description="Icecat gallery metadata for the product",
    )


class ProductCreate(ProductBase, BaseCreate):
    """Represents product create."""

    # Internal category link (resolved from supplier_subcategory at sync time).
    # Declared on the create/update schemas — NOT on ProductBase — so the field
    # is actually carried through to the table model instead of being dropped.
    category_id: uuid.UUID | None = None


class ProductUpdate(ProductBase, BaseUpdate):
    """Represents product update."""

    name: str | None = None
    description: str | None = None
    base_price: Decimal | None = None
    cost_amount: Decimal | None = None
    cost_currency: str | None = None
    customs_rate_pct: Decimal | None = None
    has_variants: bool | None = None
    category_id: uuid.UUID | None = None

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
    supplier_place_id: uuid.UUID | None = None
    overridden_fields: list[str] | None = None
    tax_rate_id: uuid.UUID | None = None
    is_featured: bool | None = None
    featured_position: int | None = None
    featured_until: datetime | None = None
    technical_specifications: list[dict[str, Any]] | None = None
    features: list[str] | None = None
    icecat_images: list[dict[str, Any]] | None = None


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


class ProductSearchRequest(SQLModel):
    """Represents product search request."""

    q: str | None = Field(default=None, max_length=200)
    category_id: uuid.UUID | None = None
    manufacturer: str | None = Field(default=None, max_length=100)
    price_min: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    price_max: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    specs: dict[str, Any] = Field(default_factory=dict)
    in_stock: bool | None = None
    limit: int = Field(default=24, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class ProductSearchFacets(SQLModel):
    """Represents product search facets."""

    manufacturers: dict[str, int] = Field(default_factory=dict)
    categories: dict[str, int] = Field(default_factory=dict)
    price_ranges: dict[str, int] = Field(default_factory=dict)


class ProductSearchResponse(SQLModel):
    """Represents product search response."""

    data: list[ProductPublic] = Field(default_factory=list)
    count: int = 0
    facets: ProductSearchFacets = Field(default_factory=ProductSearchFacets)


class ProductFeatureRequest(SQLModel):
    """Represents product feature request payload."""

    featured_position: int | None = Field(default=None, ge=0)
    featured_until: datetime | None = None
