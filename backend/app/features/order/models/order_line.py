import uuid
from decimal import Decimal

from sqlmodel import Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class OrderLineBase(Base):
    """Represents order line base."""

    order_id: uuid.UUID = Field(
        foreign_key="orders.id",
        index=True,
        description="ID de la commande",
    )
    product_id: uuid.UUID = Field(
        foreign_key="products.id",
        index=True,
        description="ID du produit",
    )
    quantity: int = Field(
        ge=1,
        description="Quantité du produit",
    )
    unit_price: Decimal = Field(
        ge=0,
        max_digits=10,
        decimal_places=2,
        description="Prix unitaire au moment de la commande",
    )
    discount_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        max_digits=10,
        decimal_places=2,
        description="Montant de la réduction appliquée",
    )
    notes: str | None = Field(
        default=None,
        max_length=500,
        description="Notes sur cette ligne de commande",
    )
    tax_rate_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="tax_rates.id",
        index=True,
        description="Snapshot du taux de taxe applique a la ligne",
    )
    cost_amount_snapshot: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=12,
        decimal_places=2,
        description="Snapshot du coût produit au moment de la commande",
    )
    cost_currency_snapshot: str | None = Field(
        default=None,
        max_length=8,
        description="Devise du coût fournisseur au moment de la commande",
    )
    fx_rate_used: Decimal | None = Field(
        default=None,
        decimal_places=6,
        max_digits=16,
        description="Taux FX utilisé pour la conversion en XPF. Null si déjà en XPF.",
    )
    customs_rate_pct_snapshot: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=8,
        decimal_places=2,
        description="Snapshot du taux de douane appliqué",
    )
    margin_rate_pct_snapshot: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=8,
        decimal_places=2,
        description="Snapshot du taux de marge appliqué",
    )
    price_group_id_snapshot: uuid.UUID | None = Field(
        default=None,
        description="Snapshot de l'ID du groupe de prix appliqué",
    )


class OrderLineCreate(OrderLineBase, BaseCreate):
    """Represents order line create."""

    pass


class OrderLineUpdate(BaseUpdate):
    """Represents order line update."""

    order_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None
    quantity: int | None = None
    unit_price: Decimal | None = None
    discount_amount: Decimal | None = None
    notes: str | None = None
    tax_rate_id: uuid.UUID | None = None


class OrderLine(OrderLineBase, table=True):
    """Represents order line."""

    __tablename__ = "order_lines"
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        description="Identifiant unique de la ligne de commande",
    )


class OrderLinePublic(OrderLineBase, BasePublic):
    """Represents order line public."""

    id: uuid.UUID


class OrderLinesPublic(SQLModel):
    """Represents order lines public."""

    data: list[OrderLinePublic] = Field(
        default_factory=list,
        description="Liste des lignes de commande",
    )
    count: int = Field(
        default=0,
        description="Nombre total de lignes de commande",
    )
