"""
Modèles de lieux physiques.
Tout lieu physique (aéroport, port, entrepôt, adresse client, île...).
"""

# mypy: disable-error-code="assignment,misc,override"

import uuid
from decimal import Decimal

from sqlalchemy import Column, Index, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate

# Zone géographique de desserte, du plus large au plus fin. La chaîne de
# destination d'une adresse remonte parent par parent (commune → île →
# archipel/région → pays) ; tout autre type est un nœud opérationnel.
GEO_PLACE_TYPES: tuple[str, ...] = ("country", "region", "island", "municipality")
NODE_PLACE_TYPES: tuple[str, ...] = (
    "warehouse",
    "seaport",
    "airport",
    "shop",
    "supplier",
    "address",
)
# Garde-fou contre un cycle parent_id accidentel lors de la remontée.
MAX_PLACE_DEPTH = 10


class PlaceBase(Base):
    """Represents place base."""

    name: str = Field(max_length=200, description="Place name")
    type: str = Field(
        max_length=50,
        index=True,
        description="Type: airport, seaport, warehouse, address, island, etc.",
    )
    parent_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="places.id",
        index=True,
        description=(
            "Parent zone (e.g. municipality → island → region → country). "
            "Null for roots and standalone operational nodes."
        ),
    )
    code: str | None = Field(
        default=None,
        max_length=50,
        index=True,
        description="Code IATA/UN/LOCODE/autre",
    )

    # Géolocalisation
    latitude: float | None = Field(default=None, description="Latitude")
    longitude: float | None = Field(default=None, description="Longitude")
    timezone: str | None = Field(default=None, max_length=50, description="Timezone")

    # Adresse complète
    address_line1: str | None = Field(default=None, max_length=200)
    address_line2: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=20)
    country: str | None = Field(
        default=None,
        max_length=2,
        index=True,
        description="Code Country ISO",
    )
    region: str | None = Field(default=None, max_length=100, description="Region/État")

    # Capacités pour entrepôts
    is_warehouse: bool = Field(
        default=False,
        index=True,
        description="Is a warehouse",
    )
    is_main_warehouse: bool = Field(
        default=False,
        index=True,
        description=(
            "The shop's main warehouse — where supplier goods converge and from "
            "where the last leg to the customer starts. Exactly one place "
            "(partial unique index); set it through POST /place/{id}/set-main-warehouse."
        ),
    )

    # Régime douanier d'un lieu d'origine (fournisseur). Null = automatique :
    # même pays que l'entrepôt principal (ou pays exempté par le réglage
    # ``customs_free_countries``) → local, sinon import. « domestic » /
    # « import » forcent le régime quel que soit le pays.
    customs_regime: str | None = Field(
        default=None,
        max_length=20,
        description=(
            "Origin place override: 'domestic' (no customs, no import freight) "
            "or 'import' (customs apply). Null = derived from the country vs "
            "the main warehouse and the customs_free_countries setting."
        ),
    )
    # Dropshipping : les colis partent de ce fournisseur directement chez le
    # client, sans transiter par l'entrepôt principal.
    dropship_enabled: bool = Field(
        default=False,
        description=(
            "Supplier place ships straight to the customer (dropshipping): the "
            "order gets a supplier → customer leg instead of supplier → main "
            "warehouse → customer."
        ),
    )
    max_capacity_m3: float | None = Field(
        default=None, description="Capacité max en m³"
    )
    current_capacity_m3: float | None = Field(
        default=None, description="Capacité actuelle en m³"
    )

    # Services disponibles
    customs_clearance: bool = Field(
        default=False, description="Dédouanement disponible"
    )
    customs_declaration_fee: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=12,
        decimal_places=2,
        description=(
            "Frais fixes dus par déclaration en douane franchie ici "
            "(redevances, participations, frais de dossier transitaire), "
            "exprimés dans la devise de référence. Facturés UNE FOIS par "
            "expédition, jamais au prorata des articles (écart F3). "
            "NULL = non renseigné, donc rien n'est facturé."
        ),
    )
    consolidation_service: bool = Field(
        default=False, description="Consolidation service"
    )
    repackaging_service: bool = Field(default=False, description="Repackaging service")

    # Horaires d'opération
    operating_hours: str | None = Field(
        default=None, max_length=50, description="Operating hours"
    )
    partner_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="partners.id",
        index=True,
        description="ID of the partner associated with this place",
    )
    is_owned: bool = Field(
        default=False, description="Indicates if the place is owned by the company"
    )


class Place(PlaceBase, table=True):
    """Represents place."""

    __tablename__ = "places"
    __table_args__ = (
        # At most one main warehouse (declared here too so create_all-based
        # test schemas enforce it like the migrated database does).
        Index(
            "uq_places_single_main_warehouse",
            "is_main_warehouse",
            unique=True,
            postgresql_where=text("is_main_warehouse"),
        ),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True),
    )


class PlaceCreate(PlaceBase, BaseCreate):
    """Represents place create."""

    pass


class PlaceUpdate(PlaceBase, BaseUpdate):
    """Represents place update."""

    name: str | None = None
    type: str | None = None
    parent_id: uuid.UUID | None = None
    code: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    timezone: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    postal_code: str | None = None
    country: str | None = None
    region: str | None = None
    is_warehouse: bool | None = None
    customs_regime: str | None = None
    dropship_enabled: bool | None = None
    max_capacity_m3: float | None = None
    current_capacity_m3: float | None = None
    customs_clearance: bool | None = None
    customs_declaration_fee: Decimal | None = None
    consolidation_service: bool | None = None
    repackaging_service: bool | None = None
    operating_hours: str | None = None


class PlacePublic(PlaceBase, BasePublic):
    """Represents place public."""

    id: uuid.UUID


class PlacesPublic(SQLModel):
    """Represents places public."""

    data: list[PlacePublic] = Field(
        default_factory=list,
        description="List of places",
    )
    count: int = Field(
        default=0,
        description="Total number of places",
    )


class PlacePostalCode(SQLModel, table=True):
    """Postal code → geographic zone mapping (e.g. 98728 → Moorea).

    Lets the address form deduce the island/zone from the postal code the
    customer typed. One postal code maps to exactly one place per country.
    """

    __tablename__ = "place_postal_codes"
    __table_args__ = (
        UniqueConstraint("country", "postal_code", name="uq_place_postal_code"),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True),
    )
    place_id: uuid.UUID = Field(
        foreign_key="places.id",
        index=True,
        description="Zone the postal code belongs to (island, municipality...)",
    )
    country: str = Field(
        max_length=2,
        index=True,
        description="ISO country code the postal code belongs to",
    )
    postal_code: str = Field(
        max_length=20,
        index=True,
        description="Exact postal code (e.g. 98728)",
    )


class PlacePostalCodesUpdate(SQLModel):
    """Replace the set of postal codes attached to a place."""

    country: str = Field(max_length=2, description="ISO country code")
    postal_codes: list[str] = Field(
        default_factory=list,
        description="Full list of postal codes for this place (replaces existing)",
    )


class PostalCodeDirectoryEntry(SQLModel):
    """A known postal code and the zone it belongs to (address-form dropdown)."""

    postal_code: str
    place_id: uuid.UUID
    place_name: str
    place_type: str


class PostalCodeDirectoryResponse(SQLModel):
    """Every registered postal code of a country, sorted by code."""

    country: str
    entries: list[PostalCodeDirectoryEntry] = Field(default_factory=list)


class PlaceResolveResponse(SQLModel):
    """Result of a postal-code → zone lookup (place is null when unknown)."""

    place: PlacePublic | None = None
    ancestors: list[PlacePublic] = Field(
        default_factory=list,
        description="Parent chain of the resolved place, nearest first",
    )


class PlaceTreeNode(SQLModel):
    """Node of the geographic zone tree (children nested)."""

    id: uuid.UUID
    name: str
    type: str
    code: str | None = None
    children: list["PlaceTreeNode"] = Field(default_factory=list)


class PlaceTreeResponse(SQLModel):
    """Represents the geographic zone tree."""

    roots: list[PlaceTreeNode] = Field(default_factory=list)
