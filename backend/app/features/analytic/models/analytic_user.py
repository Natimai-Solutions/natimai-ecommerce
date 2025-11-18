import uuid

from sqlmodel import Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class AnalyticsUserBase(Base):
    user_id: uuid.UUID = Field(foreign_key="users.id", description="ID of the user")
    login_count: int = Field(
        default=0, description="Number of times the user has logged in"
    )
    purchase_count: int = Field(
        default=0, description="Number of purchases made by the user"
    )
    average_order_value: float | None = Field(
        default=None, description="Average order value for the user"
    )
    last_login: str | None = Field(
        default=None, description="Timestamp of the last login by the user"
    )
    total_spent: float = Field(
        default=0.0, description="Total amount spent by the user"
    )
    total_orders: int = Field(
        default=0, description="Total number of orders made by the user"
    )
    favorite_products: list[uuid.UUID] = Field(
        default_factory=list, description="List of favorite product IDs"
    )


class AnalyticsUserCreate(AnalyticsUserBase, BaseCreate):
    pass


class AnalyticsUserUpdate(AnalyticsUserBase, BaseUpdate):
    user_id: uuid.UUID | None = None
    login_count: int | None = None
    purchase_count: int | None = None
    average_order_value: float | None = None
    last_login: str | None = None
    total_spent: float | None = None
    total_orders: int | None = None
    favorite_products: list[uuid.UUID] | None = None


class AnalyticsUser(AnalyticsUserBase, table=True):
    __tablename__ = "analytics_users"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)


class AnalyticsUserPublic(AnalyticsUserBase, BasePublic):
    id: uuid.UUID


class AnalyticsUsersPublic(SQLModel):
    data: list[AnalyticsUserPublic] = Field(default_factory=list)
    count: int = Field(default=0, description="Total number of analytics users")
