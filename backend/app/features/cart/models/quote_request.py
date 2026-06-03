import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class QuoteRequestBase(Base):
    """Represents quote request base."""

    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    cart_id: uuid.UUID = Field(foreign_key="carts.id", index=True)
    email: str = Field(max_length=255)
    phone: str | None = Field(default=None, max_length=255)
    full_name: str | None = Field(default=None, max_length=255)
    shipping_address: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=1000)
    status: str = Field(default="requested", max_length=50)
    items_snapshot: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))


class QuoteRequestCreate(QuoteRequestBase, BaseCreate):
    """Represents quote request create."""

    pass


class QuoteRequestUpdate(BaseUpdate):
    """Represents quote request update."""

    status: str | None = None


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
