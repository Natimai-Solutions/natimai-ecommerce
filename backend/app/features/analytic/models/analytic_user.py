# mypy: disable-error-code="assignment,misc,override"

import uuid
from decimal import Decimal

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class AnalyticsUserBase(Base):
    """Represents analytics user base."""

    user_id: uuid.UUID = Field(foreign_key="users.id", description="ID of the user")
    login_count: int = Field(
        default=0, description="Number of times the user has logged in"
    )
    purchase_count: int = Field(
        default=0, description="Number of purchases made by the user"
    )
    average_order_value: Decimal | None = Field(
        default=None,
        max_digits=10,
        decimal_places=2,
        description="Average order value for the user",
    )
    last_login: str | None = Field(
        default=None, description="Timestamp of the last login by the user"
    )
    total_spent: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        max_digits=10,
        decimal_places=2,
        description="Total amount spent by the user",
    )
    total_orders: int = Field(
        default=0, description="Total number of orders made by the user"
    )
    favorite_products: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON),
        description="List of favorite product IDs",
    )


class AnalyticsUserCreate(AnalyticsUserBase, BaseCreate):
    """Represents analytics user create."""

    pass


class AnalyticsUserUpdate(AnalyticsUserBase, BaseUpdate):
    """Represents analytics user update."""

    user_id: uuid.UUID | None = None
    login_count: int | None = None
    purchase_count: int | None = None
    average_order_value: Decimal | None = None
    last_login: str | None = None
    total_spent: Decimal | None = None
    total_orders: int | None = None
    favorite_products: list[str] | None = None


class AnalyticsUser(AnalyticsUserBase, table=True):
    """Represents analytics user."""

    __tablename__ = "analytics_users"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)


class AnalyticsUserPublic(AnalyticsUserBase, BasePublic):
    """Represents analytics user public."""

    id: uuid.UUID


class AnalyticsUsersPublic(SQLModel):
    """Represents analytics users public."""

    data: list[AnalyticsUserPublic] = Field(default_factory=list)
    count: int = Field(default=0, description="Total number of analytics users")
