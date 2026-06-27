"""Seed factories for integration tests (real DB sessions).

Each helper flushes (not commits) so the returned ORM instances stay live and
unexpired — mirroring how an endpoint receives freshly-loaded objects.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.order.models.order import Order
from app.features.order.models.order_status import OrderStatus
from app.features.place.models import Place
from app.features.shipping.models.route import ShippingRoute
from app.features.shipping.models.route_tracking import (
    ShippingRouteTracking,
    ShippingRouteTrackingConsolidation,
)
from app.features.shipping.models.status import StatusDefinition
from app.features.user.models.address import Address
from app.features.user.models.user import User


async def seed_shipping_scenario(
    session: AsyncSession, *, n_trackings: int = 2
) -> SimpleNamespace:
    """Seed a superuser, a route, an order, and a consolidation holding
    ``n_trackings`` pending trackings. Returns a namespace of live instances/ids.
    """
    admin = User(
        email=f"admin+{uuid.uuid4().hex[:8]}@test.local",
        is_superuser=True,
        is_active=True,
        hashed_password="x",
    )
    place_from = Place(name="Métropole", type="warehouse")
    place_to = Place(name="Tahiti", type="warehouse")
    session.add_all([admin, place_from, place_to])
    await session.flush()

    route = ShippingRoute(
        from_place_id=place_from.id,
        to_place_id=place_to.id,
        name="FR → PF",
        mode="sea",
    )
    order_status = OrderStatus(name="Pending")
    pending_tracking = StatusDefinition(
        entity="route_tracking", code="pending", name="En attente"
    )
    pending_consol = StatusDefinition(
        entity="consolidation", code="pending", name="En attente"
    )
    session.add_all([route, order_status, pending_tracking, pending_consol])
    await session.flush()

    order = Order(
        user_id=admin.id,
        order_status_id=order_status.id,
        total_amount=Decimal("0"),
        subtotal_amount=Decimal("0"),
        shipping_fee_amount=Decimal("0"),
        payment_fee_amount=Decimal("0"),
        total_fees_amount=Decimal("0"),
    )
    address = Address(
        user_id=admin.id,
        street="BP 1",
        city="Papeete",
        postal_code="98714",
        country="PF",
        type="shipping",
    )
    session.add_all([order, address])
    await session.flush()

    consolidation = ShippingRouteTrackingConsolidation(
        route_id=route.id,
        name="Lot 1",
        consolidation_code=f"CONS-{uuid.uuid4().hex[:8].upper()}",
        status_id=pending_consol.id,
        total_orders=n_trackings,
    )
    session.add(consolidation)
    await session.flush()

    now = datetime.now(timezone.utc)
    trackings = [
        ShippingRouteTracking(
            order_id=order.id,
            route_id=route.id,
            status_id=pending_tracking.id,
            address_id=address.id,
            consolidation_id=consolidation.id,
            sequence_order=i + 1,
            selected_at=now,
        )
        for i in range(n_trackings)
    ]
    session.add_all(trackings)
    await session.flush()

    return SimpleNamespace(
        admin=admin,
        route_id=route.id,
        order_id=order.id,
        address_id=address.id,
        consolidation_id=consolidation.id,
        tracking_ids=[t.id for t in trackings],
    )
