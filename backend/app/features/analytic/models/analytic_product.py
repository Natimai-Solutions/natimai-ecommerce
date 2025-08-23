import uuid

from sqlmodel import Field, SQLModel
from app.features.base.models import Base, BaseCreate, BaseUpdate, BasePublic


class AnalyticsProductBase(Base):
    product_id: uuid.UUID = Field(
        foreign_key="products.id", description="ID of the product"
    )
    add_to_carts: int = Field(
        default=0, description="Number of times the product has been added to carts"
    )
    purchases: int = Field(
        default=0, description="Number of times the product has been purchased"
    )
    conversion_rate: float = Field(
        default=0.0,
        description="Conversion rate of the product (purchases / add_to_carts)",
    )
    average_rating: float | None = Field(
        default=None, description="Average rating of the product"
    )
    review_count: int = Field(
        default=0, description="Number of reviews for the product"
    )


class AnalyticsProductCreate(AnalyticsProductBase, BaseCreate):
    pass


class AnalyticsProductUpdate(AnalyticsProductBase, BaseUpdate):
    pass


class AnalyticsProduct(AnalyticsProductBase, Base, table=True):
    __tablename__ = "analytic_products"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)


class AnalyticsProductPublic(AnalyticsProductBase, BasePublic):
    id: uuid.UUID


class AnalyticsProductsPublic(SQLModel):
    data: list[AnalyticsProductPublic] = Field(default_factory=list)
    count: int = Field(default=0, description="Total number of analytics products")
