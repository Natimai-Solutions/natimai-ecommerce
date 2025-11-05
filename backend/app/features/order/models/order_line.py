import uuid

from sqlmodel import Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class OrderLineBase(Base):
    order_id: uuid.UUID = Field(
        foreign_key="orders.id",
        description="ID de la commande",
    )
    product_id: uuid.UUID = Field(
        foreign_key="products.id",
        description="ID du produit",
    )
    quantity: int = Field(
        ge=1,
        description="Quantité du produit",
    )
    unit_price: float = Field(
        ge=0,
        description="Prix unitaire au moment de la commande",
    )
    discount_amount: float = Field(
        default=0.0,
        ge=0,
        description="Montant de la réduction appliquée",
    )
    notes: str | None = Field(
        default=None,
        max_length=500,
        description="Notes sur cette ligne de commande",
    )


class OrderLineCreate(OrderLineBase, BaseCreate):
    pass


class OrderLineUpdate(BaseUpdate):
    order_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None
    quantity: int | None = None
    unit_price: float | None = None
    discount_amount: float | None = None
    notes: str | None = None


class OrderLine(OrderLineBase, Base, table=True):
    __tablename__ = "order_lines"
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        description="Identifiant unique de la ligne de commande",
    )


class OrderLinePublic(OrderLineBase, BasePublic):
    id: uuid.UUID


class OrderLinesPublic(SQLModel):
    data: list[OrderLinePublic] = Field(
        default_factory=list,
        description="Liste des lignes de commande",
    )
    count: int = Field(
        default=0,
        description="Nombre total de lignes de commande",
    )
