import uuid

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.analytic.models.analytic_product import (
    AnalyticsProduct,
    AnalyticsProductCreate,
    AnalyticsProductUpdate,
)
from app.features.base.crud import CrudBase


class AnalyticsProductCrud(
    CrudBase[AnalyticsProduct, AnalyticsProductCreate, AnalyticsProductUpdate]
):
    """CRUD operations for AnalyticsProduct"""

    async def get_by_product_id(
        self, session: AsyncSession, *, product_id: uuid.UUID
    ) -> AnalyticsProduct | None:
        """Get analytics by product ID"""
        statement = select(AnalyticsProduct).where(
            AnalyticsProduct.product_id == product_id,
            col(AnalyticsProduct.is_active).is_(True),
        )
        result = await session.exec(statement)
        return result.first()


crud_analytics_product = AnalyticsProductCrud(
    model=AnalyticsProduct,
    schema_create=AnalyticsProductCreate,
    schema_update=AnalyticsProductUpdate,
    order_by=AnalyticsProduct.created_at,
    outbox_events={
        "create": "create.analytics_product",
        "update": "update.analytics_product",
        "delete": "delete.analytics_product",
    },
)
