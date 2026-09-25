import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import Sequence
from sqlmodel import JSON, Column, Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate

# Backs Order.order_number (M5). Attached to the metadata so it is created by
# both Alembic (migration e4b1c7d9a250) and SQLModel.metadata.create_all —
# the integration-test harness builds its schema from the metadata alone.
order_number_seq = Sequence("order_number_seq", metadata=SQLModel.metadata)


class DeliveryType(str, Enum):
    """Last-leg delivery mode chosen by the customer at checkout."""

    PICKUP = "pickup"  # retrait en magasin
    HOME_DELIVERY = "home_delivery"  # livraison à domicile
    AIR_FREIGHT = "air_freight"  # fret aérien (vers les archipels)


class OrderBase(Base):
    """Represents order base."""

    user_id: uuid.UUID = Field(
        foreign_key="users.id",
        index=True,
        description="ID de l'utilisateur qui a passé la commande",
    )
    order_status_id: uuid.UUID = Field(
        foreign_key="order_statuses.id",
        index=True,
        description="ID du statut de la commande",
    )
    total_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        max_digits=10,
        decimal_places=2,
        description="Montant total de la commande",
    )
    subtotal_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        max_digits=12,
        decimal_places=2,
        description="Sous-total des lignes au checkout",
    )
    shipping_fee_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        max_digits=12,
        decimal_places=2,
        description="Frais de livraison figes au checkout",
    )
    payment_fee_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        max_digits=12,
        decimal_places=2,
        description="Frais de paiement figes au checkout",
    )
    total_fees_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        max_digits=12,
        decimal_places=2,
        description="Total des frais figes au checkout",
    )
    currency: str | None = Field(
        default=None,
        max_length=8,
        description=(
            "Devise de facturation figée au checkout (null pour les commandes "
            "antérieures — on retombe alors sur la devise du paiement)"
        ),
    )
    shipping_address: str | None = Field(
        default=None,
        max_length=500,
        description="Adresse de livraison",
    )
    shipping_cost_breakdown: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSON),
        description=(
            "Snapshot detaille des couts de livraison par troncon au checkout "
            "(routes selectionnees, forfait/poids/valeur, ETA, empreinte carbone)"
        ),
    )
    notes: str | None = Field(
        default=None,
        max_length=1000,
        description="Notes sur la commande",
    )
    delivery_type: str | None = Field(
        default=None,
        max_length=50,
        description="Mode de livraison du dernier tronçon choisi au checkout",
    )
    # Départ groupé (vague) auquel la commande est rattachée : posé au checkout
    # sur le départ ouvert le plus proche, déplaçable par l'admin. Null = hors
    # départ (boutique classique).
    grouped_departure_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="grouped_departures.id",
        index=True,
        description="Départ groupé de rattachement",
    )
    # Preuve d'acceptation des CGV. La case cochée dans le front n'engage rien :
    # sans trace serveur, l'acceptation n'est pas opposable et un appel direct
    # à l'API la contourne. Horodatage + version des CGV figés au checkout.
    cgv_accepted_at: datetime | None = Field(
        default=None,
        description="Horodatage UTC de l'acceptation des CGV au checkout",
    )
    cgv_version: str | None = Field(
        default=None,
        max_length=50,
        description="Version des CGV acceptée au checkout",
    )
    # Acompte : « full » = tout payé à la commande ; « deposit » = acompte à la
    # commande (deposit_amount, frais deposit_fee_amount inclus dans le total)
    # puis solde demandé à la réception des marchandises.
    payment_plan: str = Field(
        default="full", max_length=20, description="full | deposit"
    )
    deposit_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        max_digits=12,
        decimal_places=2,
        description="Acompte versé à la commande (0 en plan full)",
    )
    deposit_fee_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        max_digits=12,
        decimal_places=2,
        description="Frais de l'option acompte, inclus dans total_fees_amount",
    )
    balance_requested_at: datetime | None = Field(
        default=None, description="Envoi de la demande de solde au client"
    )
    balance_paid_at: datetime | None = Field(
        default=None, description="Encaissement du solde"
    )


class OrderCreate(OrderBase, BaseCreate):
    """Represents order create."""

    pass


class OrderUpdate(BaseUpdate):
    """Represents order update."""

    user_id: uuid.UUID | None = None
    order_status_id: uuid.UUID | None = None
    total_amount: Decimal | None = None
    subtotal_amount: Decimal | None = None
    shipping_fee_amount: Decimal | None = None
    payment_fee_amount: Decimal | None = None
    total_fees_amount: Decimal | None = None
    currency: str | None = None
    shipping_address: str | None = None
    shipping_cost_breakdown: dict[str, Any] | None = None
    notes: str | None = None
    delivery_type: str | None = None
    grouped_departure_id: uuid.UUID | None = None
    # cgv_accepted_at / cgv_version sont volontairement absents : la preuve
    # d'acceptation est figée au checkout et ne doit pas être modifiable via
    # la route de mise à jour générique.


class Order(OrderBase, table=True):
    """Represents order."""

    __tablename__ = "orders"
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        description="Identifiant unique de la commande",
    )
    # Deliberately NOT on OrderBase: server-allocated at checkout, never
    # accepted from an OrderCreate payload (no mass assignment). Nullable —
    # orders created before M5 have none.
    order_number: str | None = Field(
        default=None,
        max_length=32,
        unique=True,
        index=True,
        description="Numéro de commande lisible (CMD-AAAA-NNNNN)",
    )


class OrderPublic(OrderBase, BasePublic):
    """Represents order public."""

    id: uuid.UUID
    order_number: str | None = None


class OrdersPublic(SQLModel):
    """Represents orders public."""

    data: list[OrderPublic] = Field(
        default_factory=list,
        description="Liste des commandes",
    )
    count: int = Field(
        default=0,
        description="Nombre total de commandes",
    )
