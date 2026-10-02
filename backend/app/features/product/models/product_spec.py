import uuid
from decimal import Decimal

from sqlmodel import Field, SQLModel

SPEC_SOURCE_ICECAT = "icecat"
SPEC_SOURCE_MANUAL = "manual"


class ProductSpec(SQLModel, table=True):
    """Normalized filterable spec extracted from Icecat technical_specifications.

    One row per (product, spec_key). Upserted by the projection service after
    each Icecat enrichment. Only canonical keys defined in spec_definitions.yaml
    are stored here; raw JSONB data stays in Product.technical_specifications.
    """

    __tablename__ = "product_specs"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    product_id: uuid.UUID = Field(
        foreign_key="products.id",
        index=True,
        description="Product this spec belongs to",
    )
    spec_key: str = Field(
        max_length=64,
        index=True,
        description="Canonical spec key from spec_definitions.yaml (ex: memory_gb)",
    )
    value_text: str | None = Field(
        default=None,
        max_length=256,
        description="Normalized enum/text value (lowercased)",
    )
    value_numeric: Decimal | None = Field(
        default=None,
        decimal_places=4,
        max_digits=16,
        description="Normalized numeric value (unit already converted to spec unit)",
    )
    unit: str | None = Field(
        default=None,
        max_length=32,
        description="Unit for numeric values (ex: GB, inch)",
    )
    source: str = Field(
        default=SPEC_SOURCE_ICECAT,
        max_length=16,
        index=True,
        description=(
            "icecat: projected from the Icecat payload (rewritten at each "
            "enrichment); manual: typed in the product form (R9 / T4), never "
            "rewritten by the projection"
        ),
    )


class SpecFacetValue(SQLModel):
    """A single facet value with its product count."""

    value_text: str | None = None
    value_numeric: Decimal | None = None
    count: int = 0


class SpecFacet(SQLModel):
    """Facet info for one canonical spec key in a category."""

    key: str
    label_fr: str
    type: str
    unit: str | None = None
    values: list[SpecFacetValue] = Field(default_factory=list)


class CategorySpecFacetsResponse(SQLModel):
    """Response for GET /categories/{id}/spec-facets."""

    category_id: uuid.UUID
    specs: list[SpecFacet] = Field(default_factory=list)


class ProductKeySpec(SQLModel):
    """One key-spec tile of the product page (ex: « Mémoire RAM » / « 16 Go »)."""

    key: str
    label: str
    value: str


class ProductKeySpecsResponse(SQLModel):
    """Response for GET /product/{id}/key-specs."""

    product_id: uuid.UUID
    specs: list[ProductKeySpec] = Field(default_factory=list)
