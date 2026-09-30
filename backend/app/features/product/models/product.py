# mypy: disable-error-code="assignment,misc,override"

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import JSON, Column, event
from sqlalchemy import Enum as SAEnum
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


class PricingMode(str, Enum):
    """How the storefront price of a product is obtained.

    * ``import`` — CAF formula: cost + variable import freight + insurance,
      then customs, margin and tax. Needs a customs rate and a weight.
    * ``domestic`` — the goods never cross the customs border (own warehouse
      or a supplier of the same customs territory): cost, margin, tax.
    * ``fixed`` — ``base_price`` is the tax-inclusive sale price typed by the
      admin; nothing is computed.
    """

    IMPORT = "import"
    DOMESTIC = "domestic"
    FIXED = "fixed"


class AvailabilityMode(str, Enum):
    """Whether a product can be ordered beyond the stock known at checkout.

    * ``stock`` — historical behaviour: local + supplier stock must cover the
      quantity and is reserved at checkout.
    * ``on_demand`` — pre-order (« sur commande ») : orderable as long as the
      supplier shows *some* stock at the last refresh, without reservation;
      bought from the supplier when the grouped departure closes.
    * ``continuous`` — always orderable (consolidated accessories), shipped
      with the next departure; no stock check at all.
    """

    STOCK = "stock"
    ON_DEMAND = "on_demand"
    CONTINUOUS = "continuous"
    # Refurbished lot: a fixed quantity (``supplier_quantity``) that must
    # cover the order and is reserved — same rule as ``stock``, but the
    # storefront says « X exemplaires restants sur ce lot » and the quantity is
    # the admin's, not the supplier sync's.
    LOT = "lot"


class ProductCondition(str, Enum):
    """New goods or a refurbished item (graded, with its own warranty)."""

    NEW = "new"
    REFURBISHED = "refurbished"


# Modes that accept an order the known stock does not cover.
BACKORDER_MODES: frozenset[str] = frozenset(
    {AvailabilityMode.ON_DEMAND.value, AvailabilityMode.CONTINUOUS.value}
)


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
        description=(
            "Sale price. In pricing_mode 'fixed' it is the tax-inclusive price "
            "set by the admin; in the computed modes it is overwritten at read "
            "time by the pricing service (0 = not priced yet)."
        ),
    )
    pricing_mode: PricingMode = Field(
        default=PricingMode.IMPORT,
        # Stored as its value ('import'), not its name, in a plain VARCHAR —
        # the migration and the admin API speak the value.
        sa_column=Column(
            SAEnum(
                PricingMode,
                values_callable=lambda enum: [m.value for m in enum],
                native_enum=False,
                length=20,
            ),
            nullable=False,
            server_default=PricingMode.IMPORT.value,
            index=True,
        ),
        description=(
            "import (CAF + customs), domestic (cost + margin + tax, no customs "
            "nor import freight) or fixed (base_price is the TTC price)"
        ),
    )
    availability_mode: AvailabilityMode = Field(
        default=AvailabilityMode.STOCK,
        sa_column=Column(
            SAEnum(
                AvailabilityMode,
                values_callable=lambda enum: [m.value for m in enum],
                native_enum=False,
                length=20,
            ),
            nullable=False,
            server_default=AvailabilityMode.STOCK.value,
            index=True,
        ),
        description=(
            "stock (must be covered and is reserved), on_demand (pre-order while "
            "the supplier shows stock, no reservation) or continuous (always "
            "orderable)"
        ),
    )
    condition: ProductCondition = Field(
        default=ProductCondition.NEW,
        sa_column=Column(
            SAEnum(
                ProductCondition,
                values_callable=lambda enum: [m.value for m in enum],
                native_enum=False,
                length=20,
            ),
            nullable=False,
            server_default=ProductCondition.NEW.value,
            index=True,
        ),
        description="new or refurbished — shown and filterable on the storefront",
    )
    condition_grade: str | None = Field(
        default=None, max_length=5, description="Refurbished grade (A, B, C…)"
    )
    battery_health_pct: int | None = Field(
        default=None, ge=0, le=100, description="Refurbished: battery health in %"
    )
    os_licence: str | None = Field(
        default=None, max_length=100, description="Refurbished: OS licence supplied"
    )
    warranty_months: int | None = Field(
        default=None, ge=0, description="Warranty duration in months"
    )
    margin_rate_pct: Decimal | None = Field(
        default=None,
        ge=0,
        decimal_places=2,
        description=(
            "Margin override for this product. None → Category."
            "default_margin_rate_pct → PriceGroup.margin_rate_pct."
        ),
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
    customs_rate_pct: Decimal | None = Field(
        default=None,
        ge=0,
        decimal_places=2,
        description=(
            "Customs rate percentage applied before margin. "
            "None → inherit Category.default_customs_rate_pct; "
            "unresolved rate makes the product non-publishable."
        ),
    )
    parent_product_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="products.id",
        index=True,
        description=(
            "Parent of this variant. A variant is a full product row (own SKU, "
            "price, stock, image); the parent is the storefront entry."
        ),
    )
    variant_options: dict[str, str] | None = Field(
        default=None,
        sa_column=Column(JSON),
        description='Option values of this variant, e.g. {"Taille": "M", "Couleur": "Noir"}',
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
        index=True,
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
    supplier_missing_since: datetime | None = Field(
        default=None,
        index=True,
        description=(
            "First time the supplier stopped returning this SKU in a price & "
            "availability response. Cleared as soon as it reappears; past the "
            "delisting grace period the product is deactivated."
        ),
    )
    is_supplier_managed: bool = Field(
        default=False,
        description="Indicates if this product is managed by a supplier",
    )
    is_draft: bool = Field(
        default=False,
        index=True,
        description=(
            "Brouillon : créé par une synchronisation ou un import chez un "
            "fournisseur réglé « nouveaux articles en brouillon », jamais "
            "montré en vitrine tant que l'admin ne l'a pas publié. Les syncs "
            "et l'enrichissement continuent de l'alimenter."
        ),
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
    identity_key: str | None = Field(
        default=None,
        max_length=200,
        index=True,
        description=(
            "Same-physical-item key across suppliers: canonical barcode "
            "('gtin:…'), else manufacturer + part number ('mpn:…'). Maintained "
            "automatically on every write (see identity listeners); drives the "
            "storefront grouping and the « autres offres »."
        ),
    )
    sale_price_cached: Decimal | None = Field(
        default=None,
        ge=0,
        decimal_places=2,
        index=True,
        description=(
            "Storefront list price materialized by the pricing service (no import "
            "leg): what the search filters, sorts and returns. Refreshed on every "
            "product write, when a rate/margin changes and nightly; None = not "
            "computed yet (the search prices it on the fly)."
        ),
    )
    sale_price_cached_at: datetime | None = Field(
        default=None, description="When sale_price_cached was last computed"
    )
    last_enrichment_sync: datetime | None = Field(
        default=None,
        description="Last synchronization timestamp for enrichment data",
    )
    published_without_enrichment: bool = Field(
        default=False,
        description=(
            "Admin decision to show the product on the storefront without "
            "waiting for Icecat enrichment (file imports, items Icecat does "
            "not know). Manual products never need it."
        ),
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
        index=True,
        description="Universal Product Code (UPC) of the product",
    )
    ean: str | None = Field(
        default=None,
        max_length=50,
        index=True,
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
    pricing_mode: PricingMode | None = None
    availability_mode: AvailabilityMode | None = None
    condition: ProductCondition | None = None
    condition_grade: str | None = None
    battery_health_pct: int | None = None
    os_licence: str | None = None
    warranty_months: int | None = None
    margin_rate_pct: Decimal | None = None
    cost_amount: Decimal | None = None
    cost_currency: str | None = None
    customs_rate_pct: Decimal | None = None
    has_variants: bool | None = None
    parent_product_id: uuid.UUID | None = None
    variant_options: dict[str, str] | None = None
    category_id: uuid.UUID | None = None
    supplier_quantity: Decimal | None = None
    supplier_price: Decimal | None = None
    supplier_price_currency: str | None = None

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
    supplier_missing_since: datetime | None = None
    is_supplier_managed: bool | None = None
    published_without_enrichment: bool | None = None
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
    supplier_missing_since: datetime | None = None
    is_supplier_managed: bool = False
    #: Search listings group the same physical item sold by several
    #: suppliers behind its cheapest offer: how many offers this entry stands
    #: for (1 = no sibling).
    offers_count: int = 1
    #: Warehouse stock (place-less ``Inventory`` row). ``None`` = not computed
    #: by this endpoint; storefront endpoints always fill it.
    local_quantity: Decimal | None = None
    #: What the checkout will accept: local + supplier stock (the latter only
    #: when the product has a supplier). ``None`` = not computed.
    available_quantity: Decimal | None = None
    #: Active variants of a parent product (0 for a plain product).
    variants_count: int = 0


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
    condition: ProductCondition | None = Field(
        default=None, description="Only new or only refurbished items"
    )
    limit: int = Field(default=24, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
    group_offers: bool = Field(
        default=True,
        description=(
            "Show a same physical item sold by several suppliers once, by its "
            "cheapest offer (offers_count tells how many it stands for)"
        ),
    )


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


class ProductOfferPublic(SQLModel):
    """One supplier's offer for a physical item (product page « autres offres »)."""

    product_id: uuid.UUID
    name: str
    is_current: bool = False
    supplier_name: str | None = None
    supplier_label: str | None = None
    is_domestic: bool = False
    pricing_mode: PricingMode = PricingMode.IMPORT
    sale_price: Decimal
    supplier_quantity: Decimal
    local_quantity: Decimal = Decimal("0.00")
    available_quantity: Decimal = Decimal("0.00")
    in_stock: bool
    image_url: str | None = None


class ProductOffersResponse(SQLModel):
    """Every storefront offer of the same item, the current product included."""

    product_id: uuid.UUID
    identity_key: str | None = None
    offers: list[ProductOfferPublic] = Field(default_factory=list)
    cheapest_product_id: uuid.UUID | None = None


class ProductFeatureRequest(SQLModel):
    """Represents product feature request payload."""

    featured_position: int | None = Field(default=None, ge=0)
    featured_until: datetime | None = None


# ---------------------------------------------------------------------------
# identity_key maintenance: every write path (sync, import, admin, merge) goes
# through the ORM, so a mapper event keeps the column right without each CRUD
# having to know about it.
# ---------------------------------------------------------------------------


def _stamp_identity_key(_mapper: Any, _connection: Any, target: Product) -> None:
    from app.features.product.services.identity import product_identity_key

    target.identity_key = product_identity_key(target)


event.listen(Product, "before_insert", _stamp_identity_key)
event.listen(Product, "before_update", _stamp_identity_key)
