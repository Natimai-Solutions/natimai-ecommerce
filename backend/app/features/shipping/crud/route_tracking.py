"""
CRUD for shipping route tracking and consolidations.
"""

# mypy: disable-error-code="arg-type,attr-defined,no-untyped-def"

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy.orm import selectinload
from sqlmodel import and_, col, desc, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase

if TYPE_CHECKING:
    from app.features.shipping.models.status import StatusDefinition, StatusTransition
from app.features.shipping.models.route_tracking import (
    ShippingRouteTracking,
    ShippingRouteTrackingConsolidation,
    ShippingRouteTrackingConsolidationCreate,
    ShippingRouteTrackingConsolidationUpdate,
    ShippingRouteTrackingCreate,
    ShippingRouteTrackingLogs,
    ShippingRouteTrackingLogsCreate,
    ShippingRouteTrackingLogsUpdate,
    ShippingRouteTrackingUpdate,
)


class ShippingRouteTrackingCrud(
    CrudBase[
        ShippingRouteTracking,
        ShippingRouteTrackingCreate,
        ShippingRouteTrackingUpdate,
    ]
):
    """Represents shipping route tracking crud."""

    async def get_by_order_id(
        self,
        session: AsyncSession,
        order_id: uuid.UUID,
    ) -> ShippingRouteTracking | None:
        """Retrieve tracking by order ID"""
        statement = select(ShippingRouteTracking).where(
            ShippingRouteTracking.order_id == order_id,
            col(ShippingRouteTracking.is_active).is_(True),
        )

        result = await session.exec(statement)
        return result.first()

    async def get_by_route_id(
        self,
        session: AsyncSession,
        route_id: uuid.UUID,
        status_filter: list[str] | None = None,
    ) -> list[ShippingRouteTracking]:
        """Retrieve trackings for a specific route"""
        conditions = [
            ShippingRouteTracking.route_id == route_id,
            col(ShippingRouteTracking.is_active).is_(True),
        ]

        if status_filter:
            from app.features.shipping.models.status import StatusDefinition

            status_subq = select(StatusDefinition.id).where(
                col(StatusDefinition.code).in_(status_filter)
            )
            conditions.append(col(ShippingRouteTracking.status_id).in_(status_subq))

        statement = (
            select(ShippingRouteTracking)
            .where(and_(*conditions))
            .order_by(col(ShippingRouteTracking.selected_at).desc())
        )

        result = await session.exec(statement)
        return list(result.all())

    async def get_status_by_code(
        self, session: AsyncSession, status_code: str, entity: str = "route_tracking"
    ) -> "StatusDefinition | None":
        """Get StatusDefinition by code and entity"""
        from app.features.shipping.models.status import StatusDefinition

        statement = select(StatusDefinition).where(
            StatusDefinition.entity == entity,
            StatusDefinition.code == status_code,
            col(StatusDefinition.is_active).is_(True),
        )

        result = await session.exec(statement)
        return result.first()

    async def get_status_by_id(
        self, session: AsyncSession, status_id: uuid.UUID
    ) -> "StatusDefinition | None":
        """Get StatusDefinition by ID."""
        from app.features.shipping.models.status import StatusDefinition

        status = await session.get(StatusDefinition, status_id)
        if not status or not status.is_active:
            return None
        return status

    async def update_status(
        self,
        session: AsyncSession,
        tracking_id: uuid.UUID,
        new_status_id: uuid.UUID | None = None,
        new_status: str | None = None,
        reason: str | None = None,
        notes: str | None = None,
        force: bool = False,
        changed_by: str | uuid.UUID | None = None,
        change_type: str = "manual",
        consolidation_id: uuid.UUID | None = None,
    ) -> ShippingRouteTracking | None:
        """Update tracking status with transition validation and logging"""
        if new_status_id is None and new_status is None:
            raise ValueError("Either 'new_status_id' or 'new_status' must be provided")

        # Backward compatibility for older internal calls using notes.
        if reason is None and notes is not None:
            reason = notes

        tracking = await self.read(session=session, id=tracking_id)

        # Get current status info
        old_status_obj = tracking.status
        old_status_code = old_status_obj.code if old_status_obj else None
        # Capture the status id now: self.update() below commits, which expires
        # these ORM instances — re-reading .id afterwards triggers a sync
        # lazy-load (MissingGreenlet) in the async session.
        old_status_id = old_status_obj.id if old_status_obj else None

        # Get new status definition
        if new_status_id is not None:
            new_status_obj = await self.get_status_by_id(session, new_status_id)
            if not new_status_obj or new_status_obj.entity != "route_tracking":
                raise ValueError(
                    f"Status '{new_status_id}' not found for entity 'route_tracking'"
                )
        else:
            new_status_obj = await self.get_status_by_code(
                session, new_status, "route_tracking"
            )
        if not new_status_obj:
            raise ValueError(
                f"Status '{new_status}' not found for entity 'route_tracking'"
            )

        new_status_code = new_status_obj.code
        new_status_id_resolved = new_status_obj.id

        # Skip if status is the same
        if old_status_code == new_status_code:
            return tracking

        # Validate status transition if not forced
        transition = None
        if not force:
            is_valid = await self.validate_status_transition(
                session=session,
                current_status=old_status_code,
                new_status=new_status_code,
                entity="route_tracking",
            )
            if not is_valid:
                raise ValueError(
                    f"Invalid status transition from '{old_status_code}' to '{new_status_code}' "
                    f"for entity 'route_tracking'"
                )

            # Get the transition for logging
            transition = await self.get_status_transition(
                session=session,
                current_status=old_status_code,
                new_status=new_status_code,
                entity="route_tracking",
            )

        # Update the tracking
        update_data = {
            "status_id": new_status_id_resolved,
            "last_status_update": datetime.utcnow(),
        }
        if reason:
            update_data["notes"] = reason

        updated_tracking = await self.update(
            session=session,
            id=tracking_id,
            record=tracking,
            data=update_data,
        )

        # Create status change log
        await self.create_status_log(
            session=session,
            tracking_id=tracking_id,
            from_status_id=old_status_id,
            to_status_id=new_status_id_resolved,
            change_type=change_type,
            consolidation_id=consolidation_id,
            changed_by=str(changed_by) if changed_by is not None else None,
            reason=reason,
            transition=transition,
        )

        return updated_tracking

    async def validate_status_transition(
        self,
        session: AsyncSession,
        current_status: str,
        new_status: str,
        entity: str = "route_tracking",
    ) -> bool:
        """Validate if a status transition is allowed"""
        from app.features.shipping.models.status import StatusTransition

        # Check if transition exists in StatusTransition table
        statement = select(StatusTransition).where(
            StatusTransition.entity == entity,
            StatusTransition.from_code == current_status,
            StatusTransition.to_code == new_status,
            col(StatusTransition.is_active).is_(True),
        )

        result = await session.exec(statement)
        transition = result.first()

        if not transition:
            # No explicit transition found - check if it's the same status (always allowed)
            return current_status == new_status

        # TODO: Implement guard validation if guard_name is set
        # if transition.guard_name:
        #     return await self.validate_guard(session, transition.guard_name, tracking)

        return True

    async def get_available_transitions(
        self,
        session: AsyncSession,
        current_status: str,
        entity: str = "route_tracking",
    ) -> list["StatusTransition"]:
        """Get available status transitions from current status"""
        from app.features.shipping.models.status import StatusTransition

        statement = select(StatusTransition).where(
            StatusTransition.entity == entity,
            StatusTransition.from_code == current_status,
            col(StatusTransition.is_active).is_(True),
        )

        result = await session.exec(statement)
        return list(result.all())

    async def get_trackings_for_consolidation(
        self,
        session: AsyncSession,
        consolidation_id: uuid.UUID,
    ) -> list[ShippingRouteTracking]:
        """Retrieve all trackings in a consolidation"""
        statement = select(ShippingRouteTracking).where(
            ShippingRouteTracking.consolidation_id == consolidation_id,
            col(ShippingRouteTracking.is_active).is_(True),
        )

        result = await session.exec(statement)
        return list(result.all())

    async def get_unconsolidated_trackings(
        self,
        session: AsyncSession,
        route_id: uuid.UUID | None = None,
    ) -> list[ShippingRouteTracking]:
        """Retrieve trackings not yet consolidated"""
        conditions = [
            col(ShippingRouteTracking.consolidation_id).is_(None),
            col(ShippingRouteTracking.is_active).is_(True),
        ]

        if route_id:
            conditions.append(ShippingRouteTracking.route_id == route_id)

        statement = (
            select(ShippingRouteTracking)
            .where(and_(*conditions))
            .order_by(col(ShippingRouteTracking.selected_at).asc())
        )

        result = await session.exec(statement)
        return list(result.all())

    async def get_trackings_by_order_sequence(
        self,
        session: AsyncSession,
        order_id: uuid.UUID,
    ) -> list[ShippingRouteTracking]:
        """Get all trackings for an order, ordered by sequence.

        Eager-loads the route (and its places via the route's selectin relations)
        and the consolidation so the customer tracking view can show the leg
        ("France → Papeete (avion)") and the order's own consolidations without
        triggering lazy loads.
        """
        statement = (
            select(ShippingRouteTracking)
            .where(
                ShippingRouteTracking.order_id == order_id,
                col(ShippingRouteTracking.is_active).is_(True),
            )
            .options(
                selectinload(ShippingRouteTracking.route),
                selectinload(ShippingRouteTracking.consolidation),
            )
            .order_by(col(ShippingRouteTracking.sequence_order).asc())
        )

        result = await session.exec(statement)
        return list(result.all())

    async def get_current_route_for_order(
        self,
        session: AsyncSession,
        order_id: uuid.UUID,
    ) -> ShippingRouteTracking | None:
        """Get the current active route for an order (not completed/delivered)"""
        from app.features.shipping.models.status import StatusDefinition

        terminal_status_subq = select(StatusDefinition.id).where(
            col(StatusDefinition.code).in_(["completed", "delivered"])
        )
        statement = (
            select(ShippingRouteTracking)
            .where(
                ShippingRouteTracking.order_id == order_id,
                col(ShippingRouteTracking.is_active).is_(True),
                col(ShippingRouteTracking.status_id).not_in(terminal_status_subq),
            )
            .order_by(col(ShippingRouteTracking.sequence_order).asc())
        )

        result = await session.exec(statement)
        return result.first()

    async def get_next_route_for_order(
        self,
        session: AsyncSession,
        order_id: uuid.UUID,
        current_sequence: int,
    ) -> ShippingRouteTracking | None:
        """Get the next route in sequence for an order"""
        statement = select(ShippingRouteTracking).where(
            ShippingRouteTracking.order_id == order_id,
            col(ShippingRouteTracking.is_active).is_(True),
            ShippingRouteTracking.sequence_order == current_sequence + 1,
        )

        result = await session.exec(statement)
        return result.first()

    async def suggest_ungroup_for_consolidation(
        self,
        session: AsyncSession,
        consolidation_id: uuid.UUID,
    ) -> bool:
        """Smart default for the « garder / dégrouper » popup.

        Suggest ungrouping when the parcels of the lot would no longer travel
        together on the next leg: the next tronçon is the last-leg (delivery to
        the customer), a parcel has no next leg, or the next legs diverge.
        """
        trackings = await self.get_trackings_for_consolidation(
            session, consolidation_id
        )
        if not trackings:
            return False
        next_route_ids: set[uuid.UUID] = set()
        for t in trackings:
            nxt = await self.get_next_route_for_order(
                session, t.order_id, t.sequence_order
            )
            if nxt is None:
                return True  # a parcel terminates here → deliver individually
            if nxt.route is not None and nxt.route.is_to_customer:
                return True  # next leg is the last-leg (warehouse → customer)
            next_route_ids.add(nxt.route_id)
        return len(next_route_ids) > 1  # parcels diverge onto different legs

    async def activate_next_route(
        self,
        session: AsyncSession,
        current_tracking_id: uuid.UUID,
        changed_by: str | uuid.UUID | None = None,
    ) -> ShippingRouteTracking | None:
        """Mark the current leg as completed and activate the next leg in the
        order's multi-hop sequence (e.g. Fournisseur → Entrepôt → Client).

        Returns the now-active next leg, or None if the current leg was the last.
        ``order_id``/``sequence_order`` are read up-front: ``update_status`` commits
        internally, which expires ``current_tracking`` (MissingGreenlet on re-read).
        """
        current_tracking = await session.get(self.model, current_tracking_id)
        if not current_tracking:
            return None

        order_id = current_tracking.order_id
        current_sequence = current_tracking.sequence_order
        actor = changed_by if changed_by is not None else "system"

        # Complete the current leg. force=True: admin-driven progression, no
        # dependency on the StatusTransition table being seeded.
        await self.update_status(
            session=session,
            tracking_id=current_tracking_id,
            new_status="completed",
            reason="Tronçon terminé, progression vers le tronçon suivant",
            changed_by=actor,
            change_type="auto_advance",
            force=True,
        )

        next_tracking = await self.get_next_route_for_order(
            session=session,
            order_id=order_id,
            current_sequence=current_sequence,
        )
        if next_tracking is None:
            return None

        # Activate the next leg; update_status returns the refreshed instance.
        return await self.update_status(
            session=session,
            tracking_id=next_tracking.id,
            new_status="in_progress",
            reason="Tronçon activé dans la séquence",
            changed_by=actor,
            change_type="auto_advance",
            force=True,
        )

    async def get_status_transition(
        self,
        session: AsyncSession,
        current_status: str,
        new_status: str,
        entity: str = "route_tracking",
    ) -> "StatusTransition | None":
        """Get the specific status transition if it exists"""
        from app.features.shipping.models.status import StatusTransition

        statement = select(StatusTransition).where(
            StatusTransition.entity == entity,
            StatusTransition.from_code == current_status,
            StatusTransition.to_code == new_status,
            col(StatusTransition.is_active).is_(True),
        )

        result = await session.exec(statement)
        return result.first()

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
        transition=None,
    ) -> None:
        """Create a status change log entry"""
        from app.features.shipping.models.route_tracking import (
            ShippingRouteTrackingLogs,
            ShippingRouteTrackingLogsCreate,
        )

        log_data = {
            "tracking_id": tracking_id,
            "from_status_id": from_status_id,
            "to_status_id": to_status_id,
            "change_type": change_type,
            "consolidation_id": consolidation_id,
            "changed_by": changed_by or "system",
            "reason": reason,
        }

        if transition:
            log_data.update(
                {
                    "transition_id": transition.id,
                    "was_auto_advance": transition.auto_advance,
                    "required_confirmation": transition.requires_confirmation,
                }
            )

        log_create = ShippingRouteTrackingLogsCreate(**log_data)
        log_entry = ShippingRouteTrackingLogs.model_validate(log_create)

        session.add(log_entry)
        await session.commit()
        await session.refresh(log_entry)

    async def get_status_history(
        self,
        session: AsyncSession,
        tracking_id: uuid.UUID,
    ) -> list[ShippingRouteTrackingLogs]:
        """Get complete status history for a tracking"""
        from app.features.shipping.models.route_tracking import (
            ShippingRouteTrackingLogs,
        )

        statement = (
            select(ShippingRouteTrackingLogs)
            .where(ShippingRouteTrackingLogs.tracking_id == tracking_id)
            .order_by(col(ShippingRouteTrackingLogs.created_at).asc())
        )

        result = await session.exec(statement)
        return list(result.all())


class ShippingRouteTrackingConsolidationCrud(
    CrudBase[
        ShippingRouteTrackingConsolidation,
        ShippingRouteTrackingConsolidationCreate,
        ShippingRouteTrackingConsolidationUpdate,
    ]
):
    """Represents shipping route tracking consolidation crud."""

    async def get_by_code(
        self,
        session: AsyncSession,
        consolidation_code: str,
    ) -> ShippingRouteTrackingConsolidation | None:
        """Retrieve consolidation by code"""
        statement = select(ShippingRouteTrackingConsolidation).where(
            ShippingRouteTrackingConsolidation.consolidation_code == consolidation_code,
            col(ShippingRouteTrackingConsolidation.is_active).is_(True),
        )

        result = await session.exec(statement)
        return result.first()

    async def get_consolidations_for_route(
        self,
        session: AsyncSession,
        route_id: uuid.UUID,
        status_filter: list[str] | None = None,
    ) -> list[ShippingRouteTrackingConsolidation]:
        """Retrieve consolidations for a route"""
        conditions = [
            ShippingRouteTrackingConsolidation.route_id == route_id,
            col(ShippingRouteTrackingConsolidation.is_active).is_(True),
        ]

        if status_filter:
            from app.features.shipping.models.status import StatusDefinition

            status_subq = select(StatusDefinition.id).where(
                col(StatusDefinition.code).in_(status_filter)
            )
            conditions.append(
                col(ShippingRouteTrackingConsolidation.status_id).in_(status_subq)
            )

        statement = (
            select(ShippingRouteTrackingConsolidation)
            .where(and_(*conditions))
            .order_by(col(ShippingRouteTrackingConsolidation.created_at).desc())
        )

        result = await session.exec(statement)
        return list(result.all())

    async def add_tracking_to_consolidation(
        self,
        session: AsyncSession,
        consolidation_id: uuid.UUID,
        tracking_id: uuid.UUID,
    ) -> bool:
        """Add a tracking to consolidation"""
        # Get the tracking
        tracking = await session.get(ShippingRouteTracking, tracking_id)
        if not tracking:
            return False

        tracking_crud = ShippingRouteTrackingCrud(
            model=ShippingRouteTracking,
            schema_create=ShippingRouteTrackingCreate,
            schema_update=ShippingRouteTrackingUpdate,
        )

        # Update tracking with consolidation ID
        await tracking_crud.update(
            session=session,
            id=tracking.id,
            record=tracking,
            data={"consolidation_id": consolidation_id},
        )

        # Update consolidation total orders
        consolidation = await session.get(self.model, consolidation_id)
        if consolidation:
            await self.update(
                session=session,
                id=consolidation.id,
                record=consolidation,
                data={"total_orders": consolidation.total_orders + 1},
            )

        return True

    async def remove_tracking_from_consolidation(
        self,
        session: AsyncSession,
        tracking_id: uuid.UUID,
    ) -> bool:
        """Remove a tracking from consolidation"""
        # Get the tracking
        tracking = await session.get(ShippingRouteTracking, tracking_id)
        if not tracking or not tracking.consolidation_id:
            return False

        tracking_crud = ShippingRouteTrackingCrud(
            model=ShippingRouteTracking,
            schema_create=ShippingRouteTrackingCreate,
            schema_update=ShippingRouteTrackingUpdate,
        )

        # Get consolidation for count update
        consolidation = await session.get(self.model, tracking.consolidation_id)

        # Remove from consolidation
        await tracking_crud.update(
            session=session,
            id=tracking.id,
            record=tracking,
            data={"consolidation_id": None},
        )

        # Update consolidation total orders
        if consolidation and consolidation.total_orders > 0:
            await self.update(
                session=session,
                id=consolidation.id,
                record=consolidation,
                data={"total_orders": consolidation.total_orders - 1},
            )

        return True

    async def update_consolidation_status(
        self,
        session: AsyncSession,
        consolidation_id: uuid.UUID,
        new_status: str,
        update_trackings: bool = True,
    ) -> ShippingRouteTrackingConsolidation | None:
        """Update consolidation status and optionally all linked trackings"""
        consolidation = await session.get(self.model, consolidation_id)
        if not consolidation:
            return None

        # Update consolidation status
        consolidation = await self.update(
            session=session,
            id=consolidation.id,
            record=consolidation,
            data={"status_code": new_status},
        )

        # Update all linked trackings if requested
        if update_trackings:
            tracking_crud = ShippingRouteTrackingCrud(
                model=ShippingRouteTracking,
                schema_create=ShippingRouteTrackingCreate,
                schema_update=ShippingRouteTrackingUpdate,
            )
            trackings = await tracking_crud.get_trackings_for_consolidation(
                session=session, consolidation_id=consolidation_id
            )

            for tracking in trackings:
                await tracking_crud.update_status(
                    session=session,
                    tracking_id=tracking.id,
                    new_status=new_status,
                    notes=f"Status updated from consolidation: {consolidation.consolidation_code}",
                    changed_by="system",
                    change_type="consolidation_override",
                    consolidation_id=consolidation_id,
                )

        return consolidation


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
                col(ShippingRouteTrackingLogs.is_active).is_(True),
            )
            .order_by(desc(ShippingRouteTrackingLogs.created_at))
            .offset(offset)
            .limit(limit)
        )

        result = await session.exec(statement)
        return list(result.all())

    async def get_by_status_change(
        self,
        session: AsyncSession,
        from_status_id: uuid.UUID | None = None,
        to_status_id: uuid.UUID | None = None,
        limit: int = 100,
    ) -> list[ShippingRouteTrackingLogs]:
        """Get logs filtered by status change (from and/or to)."""
        conditions = [col(ShippingRouteTrackingLogs.is_active).is_(True)]

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
        return list(result.all())

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
                col(ShippingRouteTrackingLogs.is_active).is_(True),
            )
            .order_by(desc(ShippingRouteTrackingLogs.created_at))
            .limit(limit)
        )

        result = await session.exec(statement)
        return list(result.all())

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
                col(ShippingRouteTrackingLogs.is_active).is_(True),
            )
            .order_by(desc(ShippingRouteTrackingLogs.created_at))
            .limit(limit)
        )

        result = await session.exec(statement)
        return list(result.all())

    async def get_auto_advanced_logs(
        self,
        session: AsyncSession,
        limit: int = 100,
    ) -> list[ShippingRouteTrackingLogs]:
        """Get all logs that were auto-advanced."""
        statement = (
            select(ShippingRouteTrackingLogs)
            .where(
                col(ShippingRouteTrackingLogs.was_auto_advance).is_(True),
                col(ShippingRouteTrackingLogs.is_active).is_(True),
            )
            .order_by(desc(ShippingRouteTrackingLogs.created_at))
            .limit(limit)
        )

        result = await session.exec(statement)
        return list(result.all())

    async def get_logs_requiring_confirmation(
        self,
        session: AsyncSession,
        limit: int = 100,
    ) -> list[ShippingRouteTrackingLogs]:
        """Get all logs that required confirmation."""
        statement = (
            select(ShippingRouteTrackingLogs)
            .where(
                col(ShippingRouteTrackingLogs.required_confirmation).is_(True),
                col(ShippingRouteTrackingLogs.is_active).is_(True),
            )
            .order_by(desc(ShippingRouteTrackingLogs.created_at))
            .limit(limit)
        )

        result = await session.exec(statement)
        return list(result.all())

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
            col(ShippingRouteTrackingLogs.created_at) >= start_date,
            col(ShippingRouteTrackingLogs.created_at) <= end_date,
            col(ShippingRouteTrackingLogs.is_active).is_(True),
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
        return list(result.all())

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

        return await self.create(session=session, data=log_data, user=None)

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
                col(ShippingRouteTrackingLogs.is_active).is_(True),
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
            col(ShippingRouteTrackingLogs.is_active).is_(True),
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
                col(ShippingRouteTrackingLogs.is_active).is_(True),
            )
            .order_by(desc(ShippingRouteTrackingLogs.created_at))
            .limit(limit)
        )

        result = await session.exec(statement)
        return list(result.all())

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


# Export CRUD instances
crud_shipping_route_tracking = ShippingRouteTrackingCrud(
    model=ShippingRouteTracking,
    schema_create=ShippingRouteTrackingCreate,
    schema_update=ShippingRouteTrackingUpdate,
)
crud_shipping_route_tracking_consolidation = ShippingRouteTrackingConsolidationCrud(
    model=ShippingRouteTrackingConsolidation,
    schema_create=ShippingRouteTrackingConsolidationCreate,
    schema_update=ShippingRouteTrackingConsolidationUpdate,
)
# Create instance for dependency injection
crud_shipping_route_tracking_logs = ShippingRouteTrackingLogsCrud(
    model=ShippingRouteTrackingLogs,
    schema_create=ShippingRouteTrackingLogsCreate,
    schema_update=ShippingRouteTrackingLogsUpdate,
)
