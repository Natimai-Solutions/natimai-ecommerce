import uuid

from sqlmodel import Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class OrderStatusBase(Base):
    name: str = Field(
        description="Nom du statut (ex: 'En attente', 'Expédiée')",
        max_length=100,
    )
    code: str = Field(
        description="Identifiant technique unique (ex: PENDING, SHIPPED)",
        max_length=50,
        unique=True,
        index=True,
    )
    sequence: int = Field(
        description="Numéro d'ordre pour tri (0, 10, 20, 30...)",
        default=0,
        ge=0,
    )
    is_final: bool = Field(
        default=False,
        description="Indique si c'est un statut final",
    )
    is_error: bool = Field(
        default=False,
        description="Indique si c'est un statut d'erreur",
    )
    is_cancellation: bool = Field(
        default=False,
        description="Indique si c'est une annulation",
    )
    color: str = Field(
        description="Couleur hexadécimale pour l'affichage (ex: #FF5733)",
        max_length=7,
        default="#6B7280",
    )
    description: str | None = Field(
        default=None,
        max_length=500,
        description="Description détaillée du statut",
    )


class OrderStatusCreate(OrderStatusBase, BaseCreate):
    pass


class OrderStatusUpdate(BaseUpdate):
    name: str | None = None
    code: str | None = None
    sequence: int | None = None
    is_final: bool | None = None
    is_error: bool | None = None
    is_cancellation: bool | None = None
    color: str | None = None
    description: str | None = None


class OrderStatus(OrderStatusBase, table=True):
    __tablename__ = "order_statuses"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)


class OrderStatusPublic(OrderStatusBase, BasePublic):
    id: uuid.UUID


class OrderStatusesPublic(SQLModel):
    data: list[OrderStatusPublic] = Field(default_factory=list)
    count: int = Field(default=0, description="Nombre total de statuts")
