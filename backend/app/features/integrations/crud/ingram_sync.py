"""
CRUD operations for Ingram Micro synchronization logs and mappings.
Provides database operations for tracking sync history and product mappings.
"""

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlmodel import and_, desc, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.integrations.models.ingram_sync import (
    IngramProductMapping,
    IngramProductMappingCreate,
    IngramProductMappingUpdate,
    IngramSyncLog,
    IngramSyncLogCreate,
    IngramSyncLogUpdate,
    SyncStatus,
    SyncType,
)


class IngramSyncLogCrud(
    CrudBase[IngramSyncLog, IngramSyncLogCreate, IngramSyncLogUpdate]
):
    """CRUD operations for Ingram Micro synchronization logs"""

    async def create_sync_log(
        self,
        session: AsyncSession,
        sync_type: SyncType,
        categories: list[str] | None = None,
        skus: list[str] | None = None,
        job_id: str | None = None,
        created_by: UUID | None = None,
    ) -> IngramSyncLog:
        """
        Create a new sync log entry

        Args:
            session: Database session
            sync_type: Type of synchronization
            categories: Product categories being synced
            skus: Specific SKUs being processed
            job_id: ARQ job ID
            created_by: User ID who triggered the sync

        Returns:
            Created sync log record
        """
        sync_data = IngramSyncLogCreate(
            sync_type=sync_type,
            status=SyncStatus.PENDING,
            categories=categories,
            skus=skus,
            job_id=job_id,
            created_by=created_by,
        )

        return await self.create(session=session, obj_in=sync_data)

    async def start_sync(
        self, session: AsyncSession, sync_log_id: UUID
    ) -> IngramSyncLog:
        """
        Mark a sync as started

        Args:
            session: Database session
            sync_log_id: Sync log ID to update

        Returns:
            Updated sync log
        """
        update_data = IngramSyncLogUpdate(
            status=SyncStatus.RUNNING, started_at=datetime.now(timezone.utc)
        )

        return await self.update(
            session=session, db_obj_id=sync_log_id, obj_in=update_data
        )

    async def complete_sync(
        self,
        session: AsyncSession,
        sync_log_id: UUID,
        status: SyncStatus,
        statistics: dict | None = None,
        error_message: str | None = None,
    ) -> IngramSyncLog:
        """
        Mark a sync as completed

        Args:
            session: Database session
            sync_log_id: Sync log ID to update
            status: Final sync status
            statistics: Sync statistics and metrics
            error_message: Error details if sync failed

        Returns:
            Updated sync log
        """
        completed_at = datetime.now(timezone.utc)

        # Calculate duration if we have start time
        sync_log = await self.get(session=session, id=sync_log_id)
        duration_seconds = None
        if sync_log and sync_log.started_at:
            duration_seconds = (completed_at - sync_log.started_at).total_seconds()

        update_data = IngramSyncLogUpdate(
            status=status,
            completed_at=completed_at,
            duration_seconds=duration_seconds,
            statistics=statistics,
            error_message=error_message,
        )

        return await self.update(
            session=session, db_obj_id=sync_log_id, obj_in=update_data
        )

    async def get_recent_syncs(
        self,
        session: AsyncSession,
        sync_type: SyncType | None = None,
        hours: int = 24,
        limit: int = 50,
    ) -> list[IngramSyncLog]:
        """
        Get recent sync logs

        Args:
            session: Database session
            sync_type: Filter by sync type
            hours: Hours to look back
            limit: Maximum number of records to return

        Returns:
            List of recent sync logs
        """
        since = datetime.now(timezone.utc) - timedelta(hours=hours)

        statement = (
            select(IngramSyncLog)
            .where(IngramSyncLog.started_at >= since)
            .order_by(desc(IngramSyncLog.started_at))
            .limit(limit)
        )

        if sync_type:
            statement = statement.where(IngramSyncLog.sync_type == sync_type)

        result = await session.exec(statement)
        return result.all()

    async def get_last_successful_sync(
        self,
        session: AsyncSession,
        sync_type: SyncType,
        categories: list[str] | None = None,
    ) -> IngramSyncLog | None:
        """
        Get the last successful sync of a specific type

        Args:
            session: Database session
            sync_type: Type of sync to find
            categories: Filter by categories (for product syncs)

        Returns:
            Last successful sync log or None
        """
        statement = (
            select(IngramSyncLog)
            .where(
                and_(
                    IngramSyncLog.sync_type == sync_type,
                    IngramSyncLog.status == SyncStatus.SUCCESS,
                )
            )
            .order_by(desc(IngramSyncLog.completed_at))
        )

        if categories:
            # This would need a more complex query to match categories
            # For now, we'll return the most recent successful sync
            pass

        result = await session.exec(statement)
        return result.first()

    async def get_sync_statistics(
        self, session: AsyncSession, days: int = 30
    ) -> dict[str, Any]:
        """
        Get aggregated sync statistics for the last N days

        Args:
            session: Database session
            days: Number of days to analyze

        Returns:
            Dictionary with sync statistics
        """
        since = datetime.now(timezone.utc) - timedelta(days=days)

        # Count syncs by status
        status_counts = await session.exec(
            select(IngramSyncLog.status, func.count(IngramSyncLog.id).label("count"))
            .where(IngramSyncLog.started_at >= since)
            .group_by(IngramSyncLog.status)
        )

        # Count syncs by type
        type_counts = await session.exec(
            select(IngramSyncLog.sync_type, func.count(IngramSyncLog.id).label("count"))
            .where(IngramSyncLog.started_at >= since)
            .group_by(IngramSyncLog.sync_type)
        )

        # Average duration for successful syncs
        avg_duration = await session.exec(
            select(func.avg(IngramSyncLog.duration_seconds)).where(
                and_(
                    IngramSyncLog.started_at >= since,
                    IngramSyncLog.status == SyncStatus.SUCCESS,
                    IngramSyncLog.duration_seconds.is_not(None),
                )
            )
        )

        return {
            "period_days": days,
            "status_breakdown": {row.status: row.count for row in status_counts.all()},
            "type_breakdown": {row.sync_type: row.count for row in type_counts.all()},
            "average_duration_seconds": avg_duration.first(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    async def cleanup_old_logs(
        self, session: AsyncSession, days_to_keep: int = 90
    ) -> int:
        """
        Clean up old sync logs

        Args:
            session: Database session
            days_to_keep: Number of days of logs to retain

        Returns:
            Number of records deleted
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_to_keep)

        # Count records to be deleted
        count_statement = select(func.count(IngramSyncLog.id)).where(
            IngramSyncLog.created_at < cutoff_date
        )
        result = await session.exec(count_statement)
        count_to_delete = result.first() or 0

        # Delete old records
        delete_statement = select(IngramSyncLog).where(
            IngramSyncLog.created_at < cutoff_date
        )
        old_logs = await session.exec(delete_statement)

        for log in old_logs.all():
            session.delete(log)

        await session.commit()

        return count_to_delete


class IngramProductMappingCrud(
    CrudBase[
        IngramProductMapping, IngramProductMappingCreate, IngramProductMappingUpdate
    ]
):
    """CRUD operations for Ingram Micro product mappings"""

    async def get_by_ingram_sku(
        self, session: AsyncSession, ingram_sku: str
    ) -> IngramProductMapping | None:
        """
        Get product mapping by Ingram SKU

        Args:
            session: Database session
            ingram_sku: Ingram Micro SKU

        Returns:
            Product mapping or None
        """
        statement = select(IngramProductMapping).where(
            IngramProductMapping.ingram_sku == ingram_sku
        )
        result = await session.exec(statement)
        return result.first()

    async def get_by_local_product_id(
        self, session: AsyncSession, product_id: UUID
    ) -> IngramProductMapping | None:
        """
        Get product mapping by local product ID

        Args:
            session: Database session
            product_id: Local product ID

        Returns:
            Product mapping or None
        """
        statement = select(IngramProductMapping).where(
            IngramProductMapping.local_product_id == product_id
        )
        result = await session.exec(statement)
        return result.first()

    async def get_sync_enabled_mappings(
        self, session: AsyncSession, limit: int | None = None
    ) -> list[IngramProductMapping]:
        """
        Get all sync-enabled product mappings

        Args:
            session: Database session
            limit: Optional limit on results

        Returns:
            List of sync-enabled mappings
        """
        statement = select(IngramProductMapping).where(
            IngramProductMapping.sync_enabled == True
        )

        if limit:
            statement = statement.limit(limit)

        result = await session.exec(statement)
        return result.all()

    async def update_last_synced(
        self,
        session: AsyncSession,
        mapping_id: UUID,
        sync_time: datetime | None = None,
    ) -> IngramProductMapping:
        """
        Update the last synced timestamp for a mapping

        Args:
            session: Database session
            mapping_id: Mapping ID to update
            sync_time: Sync timestamp (defaults to now)

        Returns:
            Updated mapping
        """
        if sync_time is None:
            sync_time = datetime.now(timezone.utc)

        update_data = IngramProductMappingUpdate(last_synced=sync_time)

        return await self.update(
            session=session, db_obj_id=mapping_id, obj_in=update_data
        )

    async def get_stale_mappings(
        self, session: AsyncSession, hours: int = 24
    ) -> list[IngramProductMapping]:
        """
        Get product mappings that haven't been synced recently

        Args:
            session: Database session
            hours: Consider mappings stale if not synced within this many hours

        Returns:
            List of stale mappings
        """
        stale_threshold = datetime.now(timezone.utc) - timedelta(hours=hours)

        statement = select(IngramProductMapping).where(
            and_(
                IngramProductMapping.sync_enabled == True,
                IngramProductMapping.last_synced < stale_threshold,
            )
        )

        result = await session.exec(statement)
        return result.all()


# Singleton instances
ingram_sync_log_crud = IngramSyncLogCrud(
    model=IngramSyncLog,
    schema_create=IngramSyncLogCreate,
    schema_update=IngramSyncLogUpdate,
)
ingram_product_mapping_crud = IngramProductMappingCrud(
    model=IngramProductMapping,
    schema_create=IngramProductMappingCreate,
    schema_update=IngramProductMappingUpdate,
)
