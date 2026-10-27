# mypy: disable-error-code="assignment,misc,override"

import uuid
from decimal import Decimal
from typing import Any

from pydantic import computed_field
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.core.content_i18n import CATEGORY_FIELDS, translation_status
from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class CategoryBase(Base):
    """Represents category base."""

    name: str = Field(
        index=True,
        max_length=100,
        description=(
            "Name of the category — the supplier sync's matching key, never "
            "rewritten by the sync itself, so an admin rename must go through "
            "display_name instead"
        ),
    )
    display_name: str | None = Field(
        default=None,
        max_length=100,
        description=(
            "Storefront title chosen by an admin; None → name. Kept apart from "
            "name so the sync keeps finding the category (A17)"
        ),
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
    translations: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
        description=(
            "Translated display_name / description per language (R9 / T3): "
            '{"en": {"display_name": "…", "_source": "<digest>"}}'
        ),
    )
    parent_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="categories.id",
        index=True,
        description=(
            "Parent category (« Réseau > WiFi > Point d'accès WiFi »). None = "
            "a top-level category. A child inherits the defaults its chain "
            "leaves unset (tax rate, customs rate, margin) and is listed "
            "under its ancestors in the storefront."
        ),
    )
    default_tax_rate_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="tax_rates.id",
        index=True,
        description=(
            "Default tax rate applied to products in this category; None → "
            "the parent category's, else the shop default"
        ),
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
    default_margin_rate_pct: Decimal | None = Field(
        default=None,
        ge=0,
        decimal_places=2,
        description=(
            "Default margin percentage for products in this category. None → "
            "the customer's price group margin applies (Product.margin_rate_pct "
            "still overrides both)."
        ),
    )


class CategoryCreate(CategoryBase, BaseCreate):
    """Represents category create."""

    pass


class CategoryUpdate(CategoryBase, BaseUpdate):
    """Represents category update."""

    parent_id: uuid.UUID | None = None
    default_tax_rate_id: uuid.UUID | None = None
    default_customs_rate_pct: Decimal | None = None
    default_margin_rate_pct: Decimal | None = None


class Category(CategoryBase, table=True):
    """Represents category."""

    __tablename__ = "categories"
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        description="Unique identifier for the category",
    )
    merged_into_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="categories.id",
        index=True,
        description=(
            "Set when this category was merged into another (A12): the row "
            "stays, inactive, so the supplier sync keeps resolving its name "
            "to the target instead of recreating it"
        ),
    )


class CategoryPublic(CategoryBase, BasePublic):
    """Represents category public."""

    id: uuid.UUID
    merged_into_id: uuid.UUID | None = None
    #: Alternative text of ``image_url`` when it is a media-library image
    #: (edited there after the upload); filled by the storefront routes.
    image_alt: str | None = None

    @computed_field
    @property
    def title(self) -> str:
        """What the storefront shows: the admin's display_name, else name."""
        return self.display_name or self.name

    @computed_field
    @property
    def translation_status(self) -> dict[str, str]:
        """Per offered language: ``ok`` / ``stale`` / ``missing`` (R9 / T3)."""
        return translation_status(
            self.translations,
            {f: getattr(self, f, None) for f in CATEGORY_FIELDS},
            CATEGORY_FIELDS,
        )


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
