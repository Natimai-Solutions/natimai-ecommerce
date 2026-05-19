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
