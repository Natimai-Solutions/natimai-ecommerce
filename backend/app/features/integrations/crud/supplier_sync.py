"""
CRUD operations for supplier synchronization logs and product mappings.

All queries are scoped by ``supplier_name`` (the adapter's machine name) so a
single set of tables serves every distributor.
"""
# mypy: disable-error-code="arg-type"

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlmodel import and_, col, desc, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.integrations.models.supplier_sync import (
    SupplierProductMapping,
    SupplierProductMappingCreate,
    SupplierProductMappingUpdate,
    SupplierSyncLog,
    SupplierSyncLogCreate,
    SupplierSyncLogUpdate,
    SyncStatus,
    SyncType,
)


class SupplierSyncLogCrud(
    CrudBase[SupplierSyncLog, SupplierSyncLogCreate, SupplierSyncLogUpdate]
):
    """CRUD operations for supplier synchronization logs"""

    async def create_sync_log(
        self,
        session: AsyncSession,
        *,
        supplier_name: str,
        sync_type: SyncType,
        categories: list[str] | None = None,
        skus: list[str] | None = None,
        job_id: str | None = None,
        created_by: UUID | None = None,
    ) -> SupplierSyncLog:
        """Create a new sync log entry for ``supplier_name``."""
        sync_data = SupplierSyncLogCreate(
            supplier_name=supplier_name,
            sync_type=sync_type,
            status=SyncStatus.PENDING,
            categories=categories,
            skus=skus,
            job_id=job_id,
            created_by=created_by,
        )
        return await self.create(session=session, data=sync_data, user=None)

    async def start_sync(
        self, session: AsyncSession, sync_log_id: UUID
    ) -> SupplierSyncLog:
        """Mark a sync as started."""
        update_data = SupplierSyncLogUpdate(
            status=SyncStatus.RUNNING, started_at=datetime.now(timezone.utc)
        )
        return await self.update(session=session, id=sync_log_id, data=update_data)

    async def complete_sync(
        self,
        session: AsyncSession,
        sync_log_id: UUID,
        status: SyncStatus,
        statistics: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> SupplierSyncLog:
        """Mark a sync as completed and compute its duration."""
        completed_at = datetime.now(timezone.utc)

        sync_log = await self.read(session=session, id=sync_log_id)
        duration_seconds = None
        if sync_log.started_at:
            duration_seconds = (completed_at - sync_log.started_at).total_seconds()

        update_data = SupplierSyncLogUpdate(
            status=status,
            completed_at=completed_at,
            duration_seconds=duration_seconds,
            statistics=statistics,
            error_message=error_message,
        )
        return await self.update(session=session, id=sync_log_id, data=update_data)

    async def get_recent_syncs(
        self,
        session: AsyncSession,
        supplier_name: str | None = None,
        sync_type: SyncType | None = None,
        hours: int = 24,
        limit: int = 50,
    ) -> list[SupplierSyncLog]:
        """Get recent sync logs, optionally filtered by supplier/type."""
        since = datetime.now(timezone.utc) - timedelta(hours=hours)

        statement = (
            select(SupplierSyncLog)
            .where(SupplierSyncLog.started_at >= since)
            .order_by(desc(SupplierSyncLog.started_at))
            .limit(limit)
        )
        if supplier_name:
            statement = statement.where(SupplierSyncLog.supplier_name == supplier_name)
        if sync_type:
            statement = statement.where(SupplierSyncLog.sync_type == sync_type)

        result = await session.exec(statement)
        return list(result.all())

    async def get_last_successful_sync(
        self,
        session: AsyncSession,
        supplier_name: str,
        sync_type: SyncType,
    ) -> SupplierSyncLog | None:
        """Get the last successful sync of a given type for ``supplier_name``."""
        statement = (
            select(SupplierSyncLog)
            .where(
                and_(
                    SupplierSyncLog.supplier_name == supplier_name,
                    SupplierSyncLog.sync_type == sync_type,
                    SupplierSyncLog.status == SyncStatus.SUCCESS,
                )
            )
            .order_by(desc(SupplierSyncLog.completed_at))
        )
        result = await session.exec(statement)
        return result.first()

    async def get_sync_statistics(
        self,
        session: AsyncSession,
        supplier_name: str | None = None,
        days: int = 30,
    ) -> dict[str, Any]:
        """Get aggregated sync statistics for the last N days."""
        since = datetime.now(timezone.utc) - timedelta(days=days)

        def _scoped(statement: Any) -> Any:
            """Execute scoped."""
            statement = statement.where(SupplierSyncLog.started_at >= since)
            if supplier_name:
                statement = statement.where(
                    SupplierSyncLog.supplier_name == supplier_name
                )
            return statement

        status_counts = await session.exec(
            _scoped(
                select(
                    SupplierSyncLog.status,
                    func.count(col(SupplierSyncLog.id)).label("count"),
                )
            ).group_by(SupplierSyncLog.status)
        )
        type_counts = await session.exec(
            _scoped(
                select(
                    SupplierSyncLog.sync_type,
                    func.count(col(SupplierSyncLog.id)).label("count"),
                )
            ).group_by(SupplierSyncLog.sync_type)
        )
        avg_duration = await session.exec(
            _scoped(
                select(func.avg(SupplierSyncLog.duration_seconds)).where(
                    and_(
                        SupplierSyncLog.status == SyncStatus.SUCCESS,
                        col(SupplierSyncLog.duration_seconds).is_not(None),
                    )
                )
            )
        )

        status_rows = status_counts.all()
        type_rows = type_counts.all()
        return {
            "supplier_name": supplier_name,
            "period_days": days,
            "status_breakdown": {row[0]: row[1] for row in status_rows},
            "type_breakdown": {row[0]: row[1] for row in type_rows},
            "average_duration_seconds": avg_duration.first(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    async def cleanup_old_logs(
        self, session: AsyncSession, days_to_keep: int = 90
    ) -> int:
        """Delete sync logs older than ``days_to_keep`` days."""
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_to_keep)

        count_statement = select(func.count(col(SupplierSyncLog.id))).where(
            SupplierSyncLog.created_at < cutoff_date
        )
        result = await session.exec(count_statement)
        count_to_delete = result.first() or 0

        delete_statement = select(SupplierSyncLog).where(
            SupplierSyncLog.created_at < cutoff_date
        )
        old_logs = await session.exec(delete_statement)
        for log in old_logs.all():
            await session.delete(log)
        await session.commit()

        return count_to_delete


class SupplierProductMappingCrud(
    CrudBase[
        SupplierProductMapping,
        SupplierProductMappingCreate,
        SupplierProductMappingUpdate,
    ]
):
    """CRUD operations for supplier product mappings"""

    async def get_by_supplier_sku(
        self, session: AsyncSession, *, supplier_name: str, supplier_sku: str
    ) -> SupplierProductMapping | None:
        """Get a product mapping by (supplier, supplier SKU)."""
        statement = (
            select(SupplierProductMapping)
            .where(
                and_(
                    SupplierProductMapping.supplier_name == supplier_name,
                    SupplierProductMapping.supplier_sku == supplier_sku,
                )
            )
            .order_by(desc(SupplierProductMapping.last_synced))
        )
        result = await session.exec(statement)
        return result.first()

    async def upsert_mapping_for_sku(
        self,
        session: AsyncSession,
        *,
        supplier_name: str,
        supplier_sku: str,
        local_product_id: UUID,
        vendor_part_number: str | None = None,
        manufacturer: str | None = None,
        sync_time: datetime | None = None,
    ) -> SupplierProductMapping:
        """Create or update the persisted mapping for a (supplier, SKU) pair."""
        if sync_time is None:
            sync_time = datetime.now(timezone.utc)

        mapping = await self.get_by_supplier_sku(
            session=session, supplier_name=supplier_name, supplier_sku=supplier_sku
        )
        if mapping is None:
            return await self.create(
                session=session,
                data=SupplierProductMappingCreate(
                    supplier_name=supplier_name,
                    supplier_sku=supplier_sku,
                    local_product_id=local_product_id,
                    vendor_part_number=vendor_part_number,
                    manufacturer=manufacturer,
                    last_synced=sync_time,
                    sync_enabled=True,
                ),
                user=None,
            )

        return await self.update(
            session=session,
            id=mapping.id,
            data=SupplierProductMappingUpdate(
                local_product_id=local_product_id,
                vendor_part_number=vendor_part_number,
                manufacturer=manufacturer,
                last_synced=sync_time,
                sync_enabled=True,
            ),
        )

    async def get_by_local_product_id(
        self, session: AsyncSession, product_id: UUID
    ) -> SupplierProductMapping | None:
        """Get a product mapping by local product ID."""
        statement = select(SupplierProductMapping).where(
            SupplierProductMapping.local_product_id == product_id
        )
        result = await session.exec(statement)
        return result.first()

    async def get_sync_enabled_mappings(
        self,
        session: AsyncSession,
        supplier_name: str | None = None,
        limit: int | None = None,
    ) -> list[SupplierProductMapping]:
        """Get all sync-enabled product mappings (optionally for one supplier)."""
        conditions = [col(SupplierProductMapping.sync_enabled).is_(True)]
        if supplier_name:
            conditions.append(SupplierProductMapping.supplier_name == supplier_name)

        statement = select(SupplierProductMapping).where(and_(*conditions))
        if limit:
            statement = statement.limit(limit)

        result = await session.exec(statement)
        return list(result.all())

    async def update_last_synced(
        self,
        session: AsyncSession,
        mapping_id: UUID,
        sync_time: datetime | None = None,
    ) -> SupplierProductMapping:
        """Update the last-synced timestamp for a mapping."""
        if sync_time is None:
            sync_time = datetime.now(timezone.utc)
        update_data = SupplierProductMappingUpdate(last_synced=sync_time)
        return await self.update(session=session, id=mapping_id, data=update_data)

    async def get_stale_mappings(
        self,
        session: AsyncSession,
        supplier_name: str | None = None,
        hours: int = 24,
    ) -> list[SupplierProductMapping]:
        """Get product mappings not synced within the last ``hours``."""
        stale_threshold = datetime.now(timezone.utc) - timedelta(hours=hours)

        conditions = [
            col(SupplierProductMapping.sync_enabled).is_(True),
            SupplierProductMapping.last_synced < stale_threshold,
        ]
        if supplier_name:
            conditions.append(SupplierProductMapping.supplier_name == supplier_name)

        statement = select(SupplierProductMapping).where(and_(*conditions))
        result = await session.exec(statement)
        return list(result.all())


# Singleton instances
supplier_sync_log_crud = SupplierSyncLogCrud(
    model=SupplierSyncLog,
    schema_create=SupplierSyncLogCreate,
    schema_update=SupplierSyncLogUpdate,
)
supplier_product_mapping_crud = SupplierProductMappingCrud(
    model=SupplierProductMapping,
    schema_create=SupplierProductMappingCreate,
    schema_update=SupplierProductMappingUpdate,
)
