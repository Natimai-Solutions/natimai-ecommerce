import uuid
from decimal import Decimal
from typing import Any

from sqlmodel import JSON, Column, Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class OrderBase(Base):
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


class OrderCreate(OrderBase, BaseCreate):
    pass


class OrderUpdate(BaseUpdate):
    user_id: uuid.UUID | None = None
    order_status_id: uuid.UUID | None = None
    total_amount: Decimal | None = None
    subtotal_amount: Decimal | None = None
    shipping_fee_amount: Decimal | None = None
    payment_fee_amount: Decimal | None = None
    total_fees_amount: Decimal | None = None
    shipping_address: str | None = None
    shipping_cost_breakdown: dict[str, Any] | None = None
    notes: str | None = None


class Order(OrderBase, table=True):
    __tablename__ = "orders"
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        description="Identifiant unique de la commande",
    )


class OrderPublic(OrderBase, BasePublic):
    id: uuid.UUID


class OrdersPublic(SQLModel):
    data: list[OrderPublic] = Field(
        default_factory=list,
        description="Liste des commandes",
    )
    count: int = Field(
        default=0,
        description="Nombre total de commandes",
    )
