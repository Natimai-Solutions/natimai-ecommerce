import uuid

from sqlmodel import Field, SQLModel
from app.domain.base_models import Base, BaseCreate, BaseUpdate, BasePublic

class AnalyticsSaleBase(Base):
    total_sales: int = Field(
        default=0, description="Total sales amount"
    )
    order_count: int = Field(
        default=0, description="Number of orders made"
    )
    average_order_value: float = Field(
        default=0.0, description="Average value of orders"
    )
    unique_customers: int = Field(
        default=0, description="Number of unique customers"
    )
    top_selling_product_id: uuid.UUID | None = Field(
        foreign_key="products.id", description="ID of the top selling product"
    )
    
class AnalyticsSaleCreate(AnalyticsSaleBase, BaseCreate):
    pass

class AnalyticsSaleUpdate(AnalyticsSaleBase, BaseUpdate):
    total_sales: int | None = None
    order_count: int | None = None
    average_order_value: float | None = None
    unique_customers: int | None = None
    top_selling_product_id: uuid.UUID | None = None

class AnalyticsSale(AnalyticsSaleBase, Base, table=True):
    __tablename__ = "analytics_sales"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)

class AnalyticsSalePublic(AnalyticsSaleBase, BasePublic):
    id: uuid.UUID

class AnalyticsSalesPublic(SQLModel):
    data: list[AnalyticsSalePublic] = Field(default_factory=list)
    count: int = Field(default=0, description="Total number of analytics sales")