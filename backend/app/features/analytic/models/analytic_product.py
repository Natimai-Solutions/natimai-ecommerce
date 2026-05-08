import uuid
from decimal import Decimal

from sqlmodel import Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class AnalyticsProductBase(Base):
    product_id: uuid.UUID = Field(
        foreign_key="products.id",
        index=True,
        description="ID of the product",
    )
    add_to_carts: int = Field(
        default=0, description="Number of times the product has been added to carts"
    )
    purchases: int = Field(
        default=0, description="Number of times the product has been purchased"
    )
    conversion_rate: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        le=100,
        max_digits=5,
        decimal_places=2,
        description="Conversion rate of the product (purchases / add_to_carts) in percentage",
    )
    average_rating: Decimal | None = Field(
        default=None,
        ge=0,
        le=5,
        max_digits=3,
        decimal_places=2,
        description="Average rating of the product (0-5)",
    )
    review_count: int = Field(
        default=0, description="Number of reviews for the product"
    )


class AnalyticsProductCreate(AnalyticsProductBase, BaseCreate):
    pass


class AnalyticsProductUpdate(AnalyticsProductBase, BaseUpdate):
    product_id: uuid.UUID | None = None
    add_to_carts: int | None = None
    purchases: int | None = None
    conversion_rate: float | None = None
    average_rating: float | None = None
    review_count: int | None = None


class AnalyticsProduct(AnalyticsProductBase, table=True):
    __tablename__ = "analytic_products"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)


class AnalyticsProductPublic(AnalyticsProductBase, BasePublic):
    id: uuid.UUID


class AnalyticsProductsPublic(SQLModel):
    data: list[AnalyticsProductPublic] = Field(default_factory=list)
    count: int = Field(default=0, description="Total number of analytics products")
