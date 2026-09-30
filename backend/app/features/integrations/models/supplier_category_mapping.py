"""Mappage des catégories d'un fournisseur vers celles de la boutique (R4 / S5).

Sans mappage, chaque **sous-catégorie** fournisseur devient une catégorie
boutique du même nom (``get_or_create_by_name``), puis l'admin fusionne ou
renomme a posteriori. Un mappage dit, pour un couple (catégorie,
sous-catégorie) d'un fournisseur :

* où ranger ses articles (``category_id``, ou vide = une catégorie au nom de
  la source, créée au besoin) ;
* ce qu'on en fait (``action``) : ``import`` (normal), ``draft`` (nouveaux
  articles en brouillon), ``deactivate`` (importés mais hors vitrine) ou
  ``skip`` (ni créés ni mis à jour).

Un mappage sur la catégorie seule (sous-catégorie vide) vaut pour toutes ses
sous-catégories sans mappage propre. Ce qui n'est pas mappé suit
``Supplier.unmapped_category_action``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel
from pydantic import Field as PydanticField
from sqlalchemy import Column, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field, SQLModel


class CategoryMappingAction(str, Enum):
    """Sort des articles d'un couple (catégorie, sous-catégorie) fournisseur."""

    IMPORT = "import"
    DRAFT = "draft"
    DEACTIVATE = "deactivate"
    SKIP = "skip"


class UnmappedCategoryAction(str, Enum):
    """Sort des articles d'une catégorie fournisseur sans mappage."""

    #: Comportement historique : catégorie au nom de la sous-catégorie.
    AUTO = "auto"
    DRAFT = "draft"
    DEACTIVATE = "deactivate"
    SKIP = "skip"


def _enum_column(enum: type[Enum], default: str) -> Column:  # type: ignore[type-arg]
    return Column(
        SAEnum(
            enum,
            values_callable=lambda e: [m.value for m in e],
            native_enum=False,
            length=20,
        ),
        nullable=False,
        server_default=default,
    )


def normalize_part(value: str | None) -> str:
    """Casse et espaces ignorés : « Portables  » et « portables » se valent."""
    return " ".join((value or "").split()).casefold()


def source_key(category: str | None, subcategory: str | None) -> str:
    """Clé unique d'un couple, par fournisseur : ``catégorie|sous-catégorie``."""
    return f"{normalize_part(category)}|{normalize_part(subcategory)}"


class SupplierCategoryMapping(SQLModel, table=True):
    """Une règle de mappage d'un fournisseur."""

    __tablename__ = "supplier_category_mappings"
    __table_args__ = (
        UniqueConstraint(
            "supplier_id", "source_key", name="uq_supplier_category_mapping_key"
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    supplier_id: uuid.UUID = Field(
        foreign_key="suppliers.id", index=True, ondelete="CASCADE"
    )
    source_category: str | None = Field(default=None, max_length=255)
    source_subcategory: str | None = Field(default=None, max_length=255)
    source_key: str = Field(max_length=520)
    category_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="categories.id",
        index=True,
        description="Catégorie boutique ; vide = au nom de la source (créée au besoin)",
    )
    action: CategoryMappingAction = Field(
        default=CategoryMappingAction.IMPORT,
        sa_column=_enum_column(CategoryMappingAction, "import"),
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CategoryMappingWrite(BaseModel):
    """Une règle envoyée par l'admin (créée ou remplacée selon sa clé)."""

    source_category: str | None = PydanticField(default=None, max_length=255)
    source_subcategory: str | None = PydanticField(default=None, max_length=255)
    category_id: uuid.UUID | None = None
    action: CategoryMappingAction = CategoryMappingAction.IMPORT


class CategoryMappingPublic(BaseModel):
    id: uuid.UUID
    source_category: str | None
    source_subcategory: str | None
    category_id: uuid.UUID | None
    category_name: str | None = None
    action: CategoryMappingAction
    updated_at: datetime


class ObservedCategory(BaseModel):
    """Un couple (catégorie, sous-catégorie) vu chez un fournisseur."""

    source_category: str | None
    source_subcategory: str | None
    #: Articles du fournisseur (en base) ou lignes du fichier portant ce couple.
    count: int
    mapping: CategoryMappingPublic | None = None
    #: Catégorie boutique que l'import retiendrait aujourd'hui (nom), ou None.
    resolved_category_name: str | None = None
    #: Ce que l'import ferait : import | draft | deactivate | skip | filtered.
    effect: str = "import"


__all__ = [
    "CategoryMappingAction",
    "CategoryMappingPublic",
    "CategoryMappingWrite",
    "ObservedCategory",
    "SupplierCategoryMapping",
    "UnmappedCategoryAction",
    "normalize_part",
    "source_key",
]
