"""
CRUD for tracking and tracking events.
"""

import uuid
from datetime import datetime

from sqlmodel import and_, or_, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.shipping.models.tracking import (
    TrackingEvent,
    TrackingEventCreate,
    TrackingEventUpdate,
)


class TrackingEventCrud(
    CrudBase[TrackingEvent, TrackingEventCreate, TrackingEventUpdate]
):
    async def get_events_for_subject(
        self,
        session: AsyncSession,
        subject_type: str,
        subject_id: uuid.UUID,
    ) -> list[TrackingEvent]:
        """Retrieve all events for a subject"""

        statement = (
            select(TrackingEvent)
            .where(
                and_(
                    TrackingEvent.subject_type == subject_type,
                    TrackingEvent.subject_id == subject_id,
                )
            )
            .order_by(TrackingEvent.occurred_at.asc())
        )

        result = await session.exec(statement)
        return result.all()

    async def get_latest_event_for_subject(
        self,
        session: AsyncSession,
        subject_type: str,
        subject_id: uuid.UUID,
    ) -> TrackingEvent | None:
        """Retrieve the latest event for a subject"""

        statement = (
            select(TrackingEvent)
            .where(
                and_(
                    TrackingEvent.subject_type == subject_type,
                    TrackingEvent.subject_id == subject_id,
                )
            )
            .order_by(TrackingEvent.occurred_at.desc())
            .limit(1)
        )

        result = await session.exec(statement)
        return result.first()

    async def get_events_by_status(
        self,
        session: AsyncSession,
        status_to: str,
        subject_type: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[TrackingEvent]:
        """Retrieve events by status cible"""

        conditions = [TrackingEvent.status_to == status_to]

        if subject_type:
            conditions.append(TrackingEvent.subject_type == subject_type)

        if start_date:
            conditions.append(TrackingEvent.occurred_at >= start_date)

        if end_date:
            conditions.append(TrackingEvent.occurred_at <= end_date)

        statement = (
            select(TrackingEvent)
            .where(and_(*conditions))
            .order_by(TrackingEvent.occurred_at.desc())
        )

        result = await session.exec(statement)
        return result.all()

    async def get_events_by_scan_ref(
        self,
        session: AsyncSession,
        scan_ref: str,
    ) -> list[TrackingEvent]:
        """Récupère les événements par référence de scan"""

        statement = (
            select(TrackingEvent)
            .where(TrackingEvent.scan_ref == scan_ref)
            .order_by(TrackingEvent.occurred_at.asc())
        )

        result = await session.exec(statement)
        return result.all()

    async def create_tracking_event(
        self,
        session: AsyncSession,
        subject_type: str,
        subject_id: uuid.UUID,
        status_to: str,
        status_from: str | None = None,
        occurred_at: datetime | None = None,
        event_type: str = "update",
        description: str | None = None,
        scan_ref: str | None = None,
        location: str | None = None,
        actor: str | None = None,
        metadata: dict | None = None,
    ) -> TrackingEvent:
        """Create a new tracking event"""

        if not occurred_at:
            occurred_at = datetime.utcnow()

        event_data = TrackingEventCreate(
            subject_type=subject_type,
            subject_id=subject_id,
            status_from=status_from,
            status_to=status_to,
            occurred_at=occurred_at,
            event_type=event_type,
            description=description,
            scan_ref=scan_ref,
            location=location,
            actor=actor,
            metadata=metadata,
        )

        return await self.create(session, obj_in=event_data)

    async def search_events(
        self,
        session: AsyncSession,
        search_term: str,
        subject_type: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[TrackingEvent]:
        """Recherche d'événements par description, localisation ou scan"""

        conditions = []

        if subject_type:
            conditions.append(TrackingEvent.subject_type == subject_type)

        if start_date:
            conditions.append(TrackingEvent.occurred_at >= start_date)

        if end_date:
            conditions.append(TrackingEvent.occurred_at <= end_date)

        # Recherche dans différents champs
        search_conditions = [
            TrackingEvent.description.ilike(f"%{search_term}%"),
            TrackingEvent.location.ilike(f"%{search_term}%"),
            TrackingEvent.scan_ref.ilike(f"%{search_term}%"),
            TrackingEvent.actor.ilike(f"%{search_term}%"),
        ]

        statement = (
            select(TrackingEvent)
            .where(and_(*conditions, or_(*search_conditions)))
            .order_by(TrackingEvent.occurred_at.desc())
        )

        result = await session.exec(statement)
        return result.all()


crud_tracking_event = TrackingEventCrud(
    model=TrackingEvent,
    schema_create=TrackingEventCreate,
    schema_update=TrackingEventUpdate,
    order_by=TrackingEvent.occurred_at.desc(),
)

