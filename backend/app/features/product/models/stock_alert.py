"""« Me prévenir » : a customer (or a visitor, by e-mail) asks to be told
when a product that cannot be ordered today becomes orderable again."""

import uuid
from datetime import datetime

from pydantic import EmailStr
from sqlmodel import Field, SQLModel

from app.features.base.models import Base, BasePublic

STOCK_ALERT_STATUSES: tuple[str, ...] = ("pending", "sent", "cancelled")


class StockAlertBase(Base):
    """Represents stock alert base."""

    product_id: uuid.UUID = Field(foreign_key="products.id", index=True)
    user_id: uuid.UUID | None = Field(default=None, foreign_key="users.id", index=True)
    email: str = Field(max_length=255, index=True)
    status: str = Field(default="pending", max_length=20, index=True)
    notified_at: datetime | None = Field(default=None)


class StockAlert(StockAlertBase, table=True):
    """Represents stock alert."""

    __tablename__ = "stock_alerts"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)


class StockAlertSubscribe(SQLModel):
    """Storefront payload; the e-mail defaults to the account's when signed in."""

    product_id: uuid.UUID
    email: EmailStr | None = None


class StockAlertPublic(StockAlertBase, BasePublic):
    """Represents stock alert public."""

    id: uuid.UUID
    product_name: str | None = None
