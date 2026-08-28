import datetime
import uuid
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class QuoteRequestStatus(str, Enum):
    """Cycle de vie d'une demande de devis, côté back-office.

    Volontairement court : le devis lui-même se négocie hors de l'application
    (email, téléphone). Ce qui doit être traçable ici, c'est qu'une demande a
    bien été prise en charge et comment elle s'est terminée.
    """

    REQUESTED = "requested"
    #: L'email vers le support a échoué — la demande existe malgré tout en base,
    #: c'est justement le cas où l'écran admin est l'unique filet.
    EMAIL_FAILED = "email_failed"
    IN_PROGRESS = "in_progress"
    QUOTED = "quoted"
    WON = "won"
    LOST = "lost"
    CANCELLED = "cancelled"


#: Statuts terminaux : ils figent `handled_at`.
CLOSED_QUOTE_STATUSES = frozenset(
    {QuoteRequestStatus.WON, QuoteRequestStatus.LOST, QuoteRequestStatus.CANCELLED}
)


class QuoteRequestBase(Base):
    """Represents quote request base."""

    # Nullable : une demande de devis peut venir d'un visiteur non connecté, qui
    # n'a ni compte ni panier serveur. Ces demandes n'étaient auparavant pas
    # persistées du tout et disparaissaient avec l'email.
    user_id: uuid.UUID | None = Field(default=None, foreign_key="users.id", index=True)
    cart_id: uuid.UUID | None = Field(default=None, foreign_key="carts.id", index=True)
    email: str = Field(max_length=255)
    phone: str | None = Field(default=None, max_length=255)
    full_name: str | None = Field(default=None, max_length=255)
    shipping_address: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=1000)
    status: str = Field(default=QuoteRequestStatus.REQUESTED, max_length=50)
    items_snapshot: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    admin_comment: str | None = Field(
        default=None,
        max_length=2000,
        description="Suivi interne : pourquoi le devis a été perdu, relances…",
    )
    handled_at: datetime.datetime | None = Field(
        default=None, description="Date de clôture de la demande"
    )
    handled_by_id: uuid.UUID | None = Field(
        default=None, foreign_key="users.id", nullable=True
    )


class QuoteRequestCreate(QuoteRequestBase, BaseCreate):
    """Represents quote request create."""

    pass


class QuoteRequestUpdate(BaseUpdate):
    """Represents quote request update."""

    status: str | None = None
    admin_comment: str | None = None


class QuoteRequest(QuoteRequestBase, table=True):
    """Represents quote request."""

    __tablename__ = "quote_requests"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)


class QuoteRequestPublic(QuoteRequestBase, BasePublic):
    """Represents quote request public."""

    id: uuid.UUID


class QuoteRequestsPublic(SQLModel):
    """Represents quote requests public."""

    data: list[QuoteRequestPublic] = Field(default_factory=list)
    count: int = Field(default=0)


class QuoteRequestResponse(SQLModel):
    """Represents quote request response."""

    quote_request_id: uuid.UUID
    email_delivered: bool
    message: str


class QuoteRequestSubmit(SQLModel):
    """Represents quote request submit payload."""

    shipping_address: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=1000)


class GuestQuoteRequestItem(SQLModel):
    """Represents a guest quote request line item."""

    product_id: uuid.UUID | None = None
    product_name: str = Field(max_length=255)
    product_image_url: str | None = Field(default=None, max_length=500)
    quantity: int = Field(ge=1)
    unit_price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    line_total: Decimal = Field(ge=0, max_digits=12, decimal_places=2)


class GuestQuoteRequestSubmit(SQLModel):
    """Represents guest quote request submit payload."""

    customer_email: str = Field(max_length=255)
    customer_name: str | None = Field(default=None, max_length=255)
    customer_phone: str | None = Field(default=None, max_length=255)
    shipping_address: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=1000)
    currency: str = Field(default="XPF", max_length=8)
    items: list[GuestQuoteRequestItem] = Field(default_factory=list)


class GuestQuoteRequestResponse(SQLModel):
    """Represents guest quote request response."""

    email_delivered: bool
    message: str
