import uuid

from sqlmodel import Field, Relationship, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class OrderBase(Base):
    user_id: uuid.UUID = Field(
        foreign_key="users.id",
        description="ID de l'utilisateur qui a passé la commande",
    )
    order_status_id: uuid.UUID = Field(
        foreign_key="order_statuses.id",
        description="ID du statut de la commande",
    )
    total_amount: float = Field(
        default=0.0,
        ge=0,
        description="Montant total de la commande",
    )
    shipping_address: str | None = Field(
        default=None,
        max_length=500,
        description="Adresse de livraison",
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
    total_amount: float | None = None
    shipping_address: str | None = None
    notes: str | None = None


class Order(OrderBase, Base, table=True):
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
