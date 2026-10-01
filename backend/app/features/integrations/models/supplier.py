"""Fournisseurs déclarés en base (table ``suppliers``).

Un fournisseur n'est plus une classe Python câblée dans le code plus un jeu de
variables ``.env`` : c'est une ligne que l'admin crée, avec son entrepôt
d'origine (un ``Place``, utilisé pour le premier tronçon logistique et le
suivi), son régime douanier et sa **méthode d'approvisionnement** :

* ``manual`` — fournisseur générique : les articles sont créés à la main
  (ou importés une fois), rien n'est synchronisé ;
* ``file`` — le fournisseur envoie un CSV / Excel : l'admin le téléverse, un
  mapping de colonnes le traduit vers nos champs, l'orchestrateur fait le
  reste comme pour une API ;
* ``api`` — une intégration existe dans le code
  (:mod:`app.services.suppliers`, clé ``adapter_key``) ; la ligne porte la
  configuration non secrète (catégories, cadence, environnement), les
  identifiants restent dans l'environnement.

``code`` est la clé de rapprochement : c'est la valeur portée par
``Product.supplier_name``, ``SupplierProductMapping.supplier_name``,
``SupplierSyncLog.supplier_name`` et ``SupplierOrder.supplier_name``. Il est
immuable après création (pas dans le schéma de mise à jour).
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, field_validator
from pydantic import Field as PydanticField
from sqlalchemy import JSON, Column, Text
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field, SQLModel

from app.features.integrations.models.supplier_category_mapping import (
    UnmappedCategoryAction,
)

_CODE_RE = re.compile(r"^[a-z0-9][a-z0-9_]{1,49}$")


class SupplierKind(str, Enum):
    """Méthode d'approvisionnement d'un fournisseur."""

    MANUAL = "manual"
    FILE = "file"
    API = "api"


#: Champs de ``NormalizedProductData`` qu'un mapping de colonnes peut viser.
#: ``supplier_sku`` et ``name`` sont obligatoires ; le reste est optionnel.
FILE_MAPPING_TARGETS: tuple[str, ...] = (
    "supplier_sku",
    "name",
    "description",
    "manufacturer",
    "vendor_part_number",
    "category",
    "subcategory",
    "price",
    "currency",
    "quantity",
    "weight",
    "image_url",
    "spec_url",
    "upc",
    "ean",
    # Refurbished lots
    "condition",
    "condition_grade",
    "battery_health_pct",
    "os_licence",
    "warranty_months",
    "availability_mode",
)
FILE_MAPPING_REQUIRED: tuple[str, ...] = ("supplier_sku", "name")


def validate_supplier_code(value: str) -> str:
    """Normaliser et valider un code fournisseur (minuscules, ``[a-z0-9_]``)."""
    code = value.strip().lower()
    if not _CODE_RE.fullmatch(code):
        raise ValueError(
            "Le code doit faire 2 à 50 caractères : lettres minuscules, "
            "chiffres et « _ », et commencer par une lettre ou un chiffre"
        )
    return code


class SupplierBase(SQLModel):
    """Champs communs des schémas fournisseur."""

    name: str = Field(max_length=150, description="Nom affiché du fournisseur")
    kind: SupplierKind = Field(
        default=SupplierKind.MANUAL,
        # Stockée par sa valeur ('api'), pas par son nom, dans un VARCHAR.
        sa_column=Column(
            SAEnum(
                SupplierKind,
                values_callable=lambda enum: [m.value for m in enum],
                native_enum=False,
                length=20,
            ),
            nullable=False,
            server_default=SupplierKind.MANUAL.value,
        ),
        description="Méthode d'approvisionnement : manual | file | api",
    )
    adapter_key: str | None = Field(
        default=None,
        max_length=50,
        description=(
            "Pour kind=api : clé de l'intégration enregistrée dans le code "
            "(ex. 'ingram_micro'). Ignoré pour les autres méthodes."
        ),
    )
    origin_place_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="places.id",
        index=True,
        description=(
            "Entrepôt d'expédition du fournisseur (Place). Recopié sur "
            "Product.supplier_place_id à la création des articles : il pilote "
            "le premier tronçon logistique et le suivi."
        ),
    )
    is_domestic: bool = Field(
        default=False,
        description=(
            "Fournisseur du même territoire douanier que notre entrepôt : ni "
            "droits de douane ni fret import dans le prix. Les articles créés "
            "depuis ce fournisseur prennent le mode de prix 'domestic'."
        ),
    )
    sync_enabled: bool = Field(
        default=True,
        description="Autorise les synchronisations (planifiées et manuelles)",
    )
    sync_interval_hours: int = Field(
        default=0,
        ge=0,
        description=(
            "Cadence de la synchronisation catalogue planifiée, en heures "
            "(kind=api uniquement ; 0 = jamais planifiée, manuelle seulement)"
        ),
    )
    default_categories: list[str] | None = Field(
        default=None,
        sa_column=Column(JSON),
        description="Catégories fournisseur synchronisées par défaut (kind=api)",
    )
    price_currency: str | None = Field(
        default=None,
        max_length=3,
        description=(
            "Devise des prix du fournisseur quand la source ne la précise pas "
            "(fichier sans colonne devise, prix saisis à la main)"
        ),
    )
    column_mapping: dict[str, str] | None = Field(
        default=None,
        sa_column=Column(JSON),
        description=(
            "kind=file : mapping {champ interne: en-tête de colonne du "
            "fichier}. Champs internes possibles : FILE_MAPPING_TARGETS."
        ),
    )
    auto_purchase_order: bool = Field(
        default=False,
        description=(
            "kind=api, intégration qui sait commander : la commande fournisseur "
            "est passée automatiquement à l'encaissement d'une commande client "
            "(hors départ groupé), livrée à l'entrepôt principal."
        ),
    )
    import_as_draft: bool = Field(
        default=False,
        description=(
            "Les articles créés par une synchronisation ou un import de ce "
            "fournisseur arrivent en brouillon (Product.is_draft) : enrichis "
            "et rafraîchis, mais invisibles en vitrine tant que l'admin ne "
            "les publie pas. Les articles existants ne sont pas concernés."
        ),
    )
    unmapped_category_action: UnmappedCategoryAction = Field(
        default=UnmappedCategoryAction.AUTO,
        sa_column=Column(
            SAEnum(
                UnmappedCategoryAction,
                values_callable=lambda enum: [m.value for m in enum],
                native_enum=False,
                length=20,
            ),
            nullable=False,
            server_default=UnmappedCategoryAction.AUTO.value,
        ),
        description=(
            "Sort d'un article dont la catégorie fournisseur n'a pas de mappage : "
            "auto (catégorie au nom de la sous-catégorie, comportement historique) "
            "| draft | deactivate | skip"
        ),
    )
    min_quantity: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=12,
        decimal_places=2,
        description=(
            "Import fichier : quantité minimale d'une ligne. En dessous, une "
            "référence nouvelle n'est pas créée et un article existant est mis "
            "à jour puis retiré de la vitrine (is_active=False). Une ligne sans "
            "quantité n'est pas jugée. Vide = pas de seuil."
        ),
    )
    min_price: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=14,
        decimal_places=2,
        description=(
            "Import fichier : prix d'achat minimal d'une ligne, dans la devise "
            "du fichier (même règle que la quantité minimale). Vide = pas de seuil."
        ),
    )
    sku_allowlist: list[str] | None = Field(
        default=None,
        sa_column=Column(JSON),
        description=(
            "Liste blanche de références fournisseur (SKU). Vide ou absente : "
            "tout le catalogue synchronisé est suivi. Renseignée : seules ces "
            "références sont créées et rafraîchies (prix / stock) ; les "
            "articles gérés par ce fournisseur hors liste sont retirés de la "
            "vitrine. Modifiée par PUT /admin/suppliers/{code}/sku-allowlist."
        ),
    )
    settings: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSON),
        description=(
            "Configuration non secrète propre à l'intégration (ex. "
            "environment, country_code pour Ingram). Jamais d'identifiants."
        ),
    )
    contact_email: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=50)
    notes: str | None = Field(default=None, max_length=2000)
    is_active: bool = Field(default=True)


class Supplier(SupplierBase, table=True):
    """Ligne de la table ``suppliers``."""

    __tablename__ = "suppliers"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    code: str = Field(
        max_length=50,
        unique=True,
        index=True,
        description="Clé de rapprochement (Product.supplier_name), immuable",
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    credentials_encrypted: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
        description=(
            "Identifiants du fournisseur (flux fichier), chiffrés par "
            "SECRETS_ENCRYPTION_KEY. Jamais renvoyés par l'API."
        ),
    )


class SupplierCreate(SupplierBase):
    """Création d'un fournisseur (le code est choisi une fois pour toutes)."""

    code: str = Field(max_length=50)

    @field_validator("code")
    @classmethod
    def _validate_code(cls, value: str) -> str:
        return validate_supplier_code(value)

    @field_validator("price_currency")
    @classmethod
    def _upper_currency(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else None


class SupplierUpdate(SQLModel):
    """Mise à jour partielle (tout est optionnel, ``code`` n'y est pas)."""

    name: str | None = None
    kind: SupplierKind | None = None
    adapter_key: str | None = None
    origin_place_id: uuid.UUID | None = None
    is_domestic: bool | None = None
    sync_enabled: bool | None = None
    sync_interval_hours: int | None = Field(default=None, ge=0)
    default_categories: list[str] | None = None
    price_currency: str | None = None
    column_mapping: dict[str, str] | None = None
    import_as_draft: bool | None = None
    auto_purchase_order: bool | None = None
    unmapped_category_action: UnmappedCategoryAction | None = None
    min_quantity: Decimal | None = Field(default=None, ge=0)
    min_price: Decimal | None = Field(default=None, ge=0)
    settings: dict[str, Any] | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    notes: str | None = None
    is_active: bool | None = None

    @field_validator("price_currency")
    @classmethod
    def _upper_currency(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else None


class SupplierPublic(SupplierBase):
    """Représentation renvoyée par l'API admin."""

    id: uuid.UUID
    code: str
    created_at: datetime
    updated_at: datetime
    #: Renseigné par la route : l'intégration ``adapter_key`` existe-t-elle et
    #: a-t-elle ses identifiants (kind=api) ? Toujours True sinon.
    configured: bool = True
    #: Des identifiants chiffrés sont enregistrés (jamais leur valeur).
    has_credentials: bool = False
    #: Renseigné par la désactivation seulement : articles du fournisseur dont
    #: le stock fournisseur a été remis à zéro (et masqués, selon le choix).
    products_withdrawn: int | None = None


class SuppliersPublic(BaseModel):
    """Liste paginée."""

    data: list[SupplierPublic]
    count: int


class AdapterDescriptor(BaseModel):
    """Une intégration disponible dans le code, pour le menu déroulant admin."""

    key: str
    display_name: str
    configured: bool = PydanticField(
        description="Les identifiants requis sont présents dans l'environnement"
    )
    settings_keys: list[str] = PydanticField(
        default_factory=list,
        description="Clés acceptées dans Supplier.settings pour cette intégration",
    )
    supports_purchase_orders: bool = PydanticField(
        default=False,
        description="L'intégration sait passer une commande fournisseur",
    )
    settings_schema: dict[str, Any] = PydanticField(
        default_factory=dict,
        description="Schéma JSON de Supplier.settings (formulaire admin)",
    )
