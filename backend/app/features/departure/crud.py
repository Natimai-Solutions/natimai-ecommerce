"""CRUD and queries for grouped departures."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.departure.models import (
    GroupedDeparture,
    GroupedDepartureCreate,
    GroupedDepartureUpdate,
)
from app.features.order.models.order import Order


def utcnow() -> datetime:
    """Aware UTC now — one place to patch in tests."""
    return datetime.now(timezone.utc)


class GroupedDepartureCrud(
    CrudBase[GroupedDeparture, GroupedDepartureCreate, GroupedDepartureUpdate]
):
    """Represents grouped departure crud."""

    async def get_next_open(
        self, session: AsyncSession, *, now: datetime | None = None
    ) -> GroupedDeparture | None:
        """The open, published departure whose cutoff is the nearest in the future.

        Orders are attached to it at checkout. ``None`` when no departure is
        open: the shop then behaves exactly as before departures existed.
        """
        statement = (
            select(GroupedDeparture)
            .where(
                col(GroupedDeparture.is_active).is_(True),
                col(GroupedDeparture.is_published).is_(True),
                GroupedDeparture.status == "open",
                GroupedDeparture.order_cutoff_at > (now or utcnow()),
            )
            .order_by(col(GroupedDeparture.order_cutoff_at).asc())
            .limit(1)
        )
        return (await session.exec(statement)).first()

    async def order_totals(
        self, session: AsyncSession, departure_ids: Iterable[uuid.UUID]
    ) -> dict[uuid.UUID, tuple[int, Decimal]]:
        """``{departure_id: (orders_count, orders_total)}`` in one query."""
        ids = list(departure_ids)
        if not ids:
            return {}
        statement = (
            select(
                col(Order.grouped_departure_id),
                func.count(col(Order.id)),
                func.coalesce(func.sum(col(Order.total_amount)), 0),
            )
            .where(
                col(Order.grouped_departure_id).in_(ids),
                col(Order.is_active).is_(True),
            )
            .group_by(col(Order.grouped_departure_id))
        )
        rows = (await session.exec(statement)).all()
        return {row[0]: (int(row[1]), Decimal(row[2])) for row in rows if row[0]}

    async def assign_orders(
        self,
        session: AsyncSession,
        *,
        order_ids: Iterable[uuid.UUID],
        departure_id: uuid.UUID | None,
    ) -> int:
        """Attach (or detach with ``None``) orders to a departure. Returns the
        number of orders updated. Commits."""
        ids = list(order_ids)
        if not ids:
            return 0
        orders = (await session.exec(select(Order).where(col(Order.id).in_(ids)))).all()
        for order in orders:
            order.grouped_departure_id = departure_id
            session.add(order)
        await session.commit()
        return len(orders)


crud_grouped_departure = GroupedDepartureCrud(
    model=GroupedDeparture,
    schema_create=GroupedDepartureCreate,
    schema_update=GroupedDepartureUpdate,
    order_by=col(GroupedDeparture.order_cutoff_at).desc(),
)
