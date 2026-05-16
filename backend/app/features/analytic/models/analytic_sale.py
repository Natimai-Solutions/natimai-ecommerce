# mypy: disable-error-code="assignment,misc,override"

import uuid
from decimal import Decimal

from sqlmodel import Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class AnalyticsSaleBase(Base):
    """Represents analytics sale base."""

    total_sales: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        max_digits=12,
        decimal_places=2,
        description="Total sales amount",
    )
    order_count: int = Field(default=0, description="Number of orders made")
    average_order_value: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        max_digits=10,
        decimal_places=2,
        description="Average value of orders",
    )
    unique_customers: int = Field(default=0, description="Number of unique customers")
    top_selling_product_id: uuid.UUID | None = Field(
        foreign_key="products.id", description="ID of the top selling product"
    )


class AnalyticsSaleCreate(AnalyticsSaleBase, BaseCreate):
    """Represents analytics sale create."""

    pass


class AnalyticsSaleUpdate(AnalyticsSaleBase, BaseUpdate):
    """Represents analytics sale update."""

    total_sales: Decimal | None = None
    order_count: int | None = None
    average_order_value: Decimal | None = None
    unique_customers: int | None = None
    top_selling_product_id: uuid.UUID | None = None


class AnalyticsSale(AnalyticsSaleBase, table=True):
    """Represents analytics sale."""

    __tablename__ = "analytics_sales"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)


class AnalyticsSalePublic(AnalyticsSaleBase, BasePublic):
    """Represents analytics sale public."""

    id: uuid.UUID


class AnalyticsSalesPublic(SQLModel):
    """Represents analytics sales public."""

    data: list[AnalyticsSalePublic] = Field(default_factory=list)
    count: int = Field(default=0, description="Total number of analytics sales")
