import uuid

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.analytic.models.analytic_user import (
    AnalyticsUser,
    AnalyticsUserCreate,
    AnalyticsUserUpdate,
)
from app.features.base.crud import CrudBase


class AnalyticsUserCrud(
    CrudBase[AnalyticsUser, AnalyticsUserCreate, AnalyticsUserUpdate]
):
    """CRUD operations for AnalyticsUser"""

    async def get_by_user_id(
        self, session: AsyncSession, *, user_id: uuid.UUID
    ) -> AnalyticsUser | None:
        """Get analytics by user ID"""
        statement = select(AnalyticsUser).where(
            AnalyticsUser.user_id == user_id,
            col(AnalyticsUser.is_active).is_(True),
        )
        result = await session.exec(statement)
        return result.first()


crud_analytics_user = AnalyticsUserCrud(
    model=AnalyticsUser,
    schema_create=AnalyticsUserCreate,
    schema_update=AnalyticsUserUpdate,
    order_by=AnalyticsUser.created_at,
    outbox_events={
        "create": "create.analytics_user",
        "update": "update.analytics_user",
        "delete": "delete.analytics_user",
    },
)
