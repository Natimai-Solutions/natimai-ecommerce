"""
CRUD for shipping route tracking logs.
"""

import uuid
from datetime import datetime

from sqlmodel import and_, desc, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.shipping.models.route_tracking import (
    ShippingRouteTrackingLogs,
    ShippingRouteTrackingLogsCreate,
    ShippingRouteTrackingLogsUpdate,
)


class ShippingRouteTrackingLogsCrud(
    CrudBase[
        ShippingRouteTrackingLogs,
        ShippingRouteTrackingLogsCreate,
        ShippingRouteTrackingLogsUpdate,
    ]
):
    """CRUD operations for shipping route tracking logs."""

    async def get_by_tracking_id(
        self,
        session: AsyncSession,
        tracking_id: uuid.UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ShippingRouteTrackingLogs]:
        """Get all logs for a specific tracking ID, ordered by creation date descending."""
        statement = (
            select(ShippingRouteTrackingLogs)
            .where(
                ShippingRouteTrackingLogs.tracking_id == tracking_id,
                ShippingRouteTrackingLogs.is_active.is_(True),
            )
            .order_by(desc(ShippingRouteTrackingLogs.created_at))
            .offset(offset)
            .limit(limit)
        )

        result = await session.exec(statement)
        return result.all()

    async def get_by_status_change(
        self,
        session: AsyncSession,
        from_status_id: uuid.UUID | None = None,
        to_status_id: uuid.UUID | None = None,
        limit: int = 100,
    ) -> list[ShippingRouteTrackingLogs]:
        """Get logs filtered by status change (from and/or to)."""
        conditions = [ShippingRouteTrackingLogs.is_active.is_(True)]

        if from_status_id is not None:
            conditions.append(
                ShippingRouteTrackingLogs.from_status_id == from_status_id
            )

        if to_status_id is not None:
            conditions.append(ShippingRouteTrackingLogs.to_status_id == to_status_id)

        statement = (
            select(ShippingRouteTrackingLogs)
            .where(and_(*conditions))
            .order_by(desc(ShippingRouteTrackingLogs.created_at))
            .limit(limit)
        )

        result = await session.exec(statement)
        return result.all()

    async def get_by_change_type(
        self,
        session: AsyncSession,
        change_type: str,
        limit: int = 100,
    ) -> list[ShippingRouteTrackingLogs]:
        """Get logs filtered by change type (direct, consolidation_override, auto_advance, manual)."""
        statement = (
            select(ShippingRouteTrackingLogs)
            .where(
                ShippingRouteTrackingLogs.change_type == change_type,
                ShippingRouteTrackingLogs.is_active.is_(True),
            )
            .order_by(desc(ShippingRouteTrackingLogs.created_at))
            .limit(limit)
        )

        result = await session.exec(statement)
        return result.all()

    async def get_by_consolidation_id(
        self,
        session: AsyncSession,
        consolidation_id: uuid.UUID,
        limit: int = 100,
    ) -> list[ShippingRouteTrackingLogs]:
        """Get logs for a specific consolidation."""
        statement = (
            select(ShippingRouteTrackingLogs)
            .where(
                ShippingRouteTrackingLogs.consolidation_id == consolidation_id,
                ShippingRouteTrackingLogs.is_active.is_(True),
            )
            .order_by(desc(ShippingRouteTrackingLogs.created_at))
            .limit(limit)
        )

        result = await session.exec(statement)
        return result.all()

    async def get_auto_advanced_logs(
        self,
        session: AsyncSession,
        limit: int = 100,
    ) -> list[ShippingRouteTrackingLogs]:
        """Get all logs that were auto-advanced."""
        statement = (
            select(ShippingRouteTrackingLogs)
            .where(
                ShippingRouteTrackingLogs.was_auto_advance.is_(True),
                ShippingRouteTrackingLogs.is_active.is_(True),
            )
            .order_by(desc(ShippingRouteTrackingLogs.created_at))
            .limit(limit)
        )

        result = await session.exec(statement)
        return result.all()

    async def get_logs_requiring_confirmation(
        self,
        session: AsyncSession,
        limit: int = 100,
    ) -> list[ShippingRouteTrackingLogs]:
        """Get all logs that required confirmation."""
        statement = (
            select(ShippingRouteTrackingLogs)
            .where(
                ShippingRouteTrackingLogs.required_confirmation.is_(True),
                ShippingRouteTrackingLogs.is_active.is_(True),
            )
            .order_by(desc(ShippingRouteTrackingLogs.created_at))
            .limit(limit)
        )

        result = await session.exec(statement)
        return result.all()

    async def get_logs_by_date_range(
        self,
        session: AsyncSession,
        start_date: datetime,
        end_date: datetime,
        tracking_id: uuid.UUID | None = None,
        limit: int = 500,
    ) -> list[ShippingRouteTrackingLogs]:
        """Get logs within a specific date range, optionally filtered by tracking ID."""
        conditions = [
            ShippingRouteTrackingLogs.created_at >= start_date,
            ShippingRouteTrackingLogs.created_at <= end_date,
            ShippingRouteTrackingLogs.is_active.is_(True),
        ]

        if tracking_id is not None:
            conditions.append(ShippingRouteTrackingLogs.tracking_id == tracking_id)

        statement = (
            select(ShippingRouteTrackingLogs)
            .where(and_(*conditions))
            .order_by(desc(ShippingRouteTrackingLogs.created_at))
            .limit(limit)
        )

        result = await session.exec(statement)
        return result.all()

    async def create_status_log(
        self,
        session: AsyncSession,
        tracking_id: uuid.UUID,
        from_status_id: uuid.UUID | None,
        to_status_id: uuid.UUID,
        change_type: str = "manual",
        consolidation_id: uuid.UUID | None = None,
        changed_by: str | None = None,
        reason: str | None = None,
        transition_id: uuid.UUID | None = None,
        was_auto_advance: bool = False,
        required_confirmation: bool = False,
    ) -> ShippingRouteTrackingLogs:
        """Create a new status change log entry."""
        log_data = ShippingRouteTrackingLogsCreate(
            tracking_id=tracking_id,
            from_status_id=from_status_id,
            to_status_id=to_status_id,
            change_type=change_type,
            consolidation_id=consolidation_id,
            changed_by=changed_by,
            reason=reason,
            transition_id=transition_id,
            was_auto_advance=was_auto_advance,
            required_confirmation=required_confirmation,
        )

        return await self.create(session=session, obj_in=log_data)

    async def get_latest_status_for_tracking(
        self,
        session: AsyncSession,
        tracking_id: uuid.UUID,
    ) -> ShippingRouteTrackingLogs | None:
        """Get the most recent status change for a tracking."""
        statement = (
            select(ShippingRouteTrackingLogs)
            .where(
                ShippingRouteTrackingLogs.tracking_id == tracking_id,
                ShippingRouteTrackingLogs.is_active.is_(True),
            )
            .order_by(desc(ShippingRouteTrackingLogs.created_at))
            .limit(1)
        )

        result = await session.exec(statement)
        return result.first()

    async def count_status_changes(
        self,
        session: AsyncSession,
        tracking_id: uuid.UUID,
        change_type: str | None = None,
    ) -> int:
        """Count the number of status changes for a tracking, optionally filtered by type."""
        conditions = [
            ShippingRouteTrackingLogs.tracking_id == tracking_id,
            ShippingRouteTrackingLogs.is_active.is_(True),
        ]

        if change_type is not None:
            conditions.append(ShippingRouteTrackingLogs.change_type == change_type)

        statement = select(ShippingRouteTrackingLogs).where(and_(*conditions))

        result = await session.exec(statement)
        return len(result.all())

    async def get_status_transition_history(
        self,
        session: AsyncSession,
        from_status_id: uuid.UUID,
        to_status_id: uuid.UUID,
        limit: int = 100,
    ) -> list[ShippingRouteTrackingLogs]:
        """Get history of transitions between two specific statuses."""
        statement = (
            select(ShippingRouteTrackingLogs)
            .where(
                ShippingRouteTrackingLogs.from_status_id == from_status_id,
                ShippingRouteTrackingLogs.to_status_id == to_status_id,
                ShippingRouteTrackingLogs.is_active.is_(True),
            )
            .order_by(desc(ShippingRouteTrackingLogs.created_at))
            .limit(limit)
        )

        result = await session.exec(statement)
        return result.all()

    async def soft_delete_logs_for_tracking(
        self,
        session: AsyncSession,
        tracking_id: uuid.UUID,
    ) -> int:
        """Soft delete all logs for a tracking (set is_active=False)."""
        logs = await self.get_by_tracking_id(session, tracking_id)

        count = 0
        for log in logs:
            if log.is_active:
                log.is_active = False
                session.add(log)
                count += 1

        await session.commit()
        return count


# Create instance for dependency injection
crud_shipping_route_tracking_logs = ShippingRouteTrackingLogsCrud(
    model=ShippingRouteTrackingLogs,
    schema_create=ShippingRouteTrackingLogsCreate,
    schema_update=ShippingRouteTrackingLogsUpdate,
)
