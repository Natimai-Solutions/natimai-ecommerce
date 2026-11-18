"""The import leg a price is computed on.

An import-mode product is priced freight included: the variable freight of
the import route (price per kg × billable weight) enters the customs base,
and so the margin and the tax. The storefront lets the customer choose the
route by its ``service_level`` (rapide / économique…).

Until November 2026 a price asked without a route was computed with **no
freight at all** — and that is what the catalogue, the cart and the order
did, while the product page showed the freight-inclusive price of the chosen
mode and the checkout skipped the import leg as « already in the price ».
The import freight was billed nowhere.

One rule now: no route given means the **default import route**; a line that
carries a service level is priced on that level's route.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.shipping.models.route import ShippingRoute

_SESSION_KEY = "import_routes_by_level"


@dataclass(frozen=True)
class ImportRoute:
    """What the price formula reads on an import route, as plain values (the
    pricing context outlives the caller's commits)."""

    id: uuid.UUID
    service_level: str | None
    price_per_kg: Decimal
    mode: str | None
    route_metadata: Any = None
    customer_label: str | None = None
    eta_days: int | None = None
    is_default_import: bool = False


def _snapshot(route: ShippingRoute) -> ImportRoute:
    return ImportRoute(
        id=route.id,
        service_level=route.service_level,
        price_per_kg=Decimal(route.price_per_kg or 0),
        mode=getattr(route, "mode", None),
        route_metadata=route.route_metadata,
        customer_label=route.customer_label,
        eta_days=getattr(route, "eta_days", None),
        is_default_import=bool(route.is_default_import),
    )


async def import_routes(session: AsyncSession) -> list[ImportRoute]:
    """The import routes on offer, the default one first.

    Active routes with a service level; the flagged default first, then by
    priority — the order the product page lists them in. Kept on the session
    for the request.
    """
    info = getattr(session, "info", None)
    if isinstance(info, dict):
        cached = info.get(_SESSION_KEY)
        if isinstance(cached, list):
            return cached
    rows = (
        await session.exec(
            select(ShippingRoute)
            .where(
                col(ShippingRoute.service_level).is_not(None),
                col(ShippingRoute.is_active).is_(True),
            )
            .order_by(
                col(ShippingRoute.is_default_import).desc(),
                col(ShippingRoute.priority).asc(),
                col(ShippingRoute.id).asc(),
            )
        )
    ).all()
    routes = [_snapshot(row) for row in rows if isinstance(row, ShippingRoute)]
    if isinstance(info, dict):
        info[_SESSION_KEY] = routes
    return routes


def forget_import_routes(session: AsyncSession) -> None:
    """Drop the request's copy (after a route was written)."""
    info = getattr(session, "info", None)
    if isinstance(info, dict):
        info.pop(_SESSION_KEY, None)


async def default_import_route(session: AsyncSession) -> ImportRoute | None:
    """The route a price is computed on when none is chosen."""
    routes = await import_routes(session)
    return routes[0] if routes else None


async def import_route_for_level(
    session: AsyncSession, service_level: str | None
) -> ImportRoute | None:
    """The route of ``service_level``; the default one when the level is
    empty, unknown or no longer on offer (never « no freight »)."""
    routes = await import_routes(session)
    if service_level:
        for route in routes:
            if route.service_level == service_level:
                return route
    return routes[0] if routes else None


async def import_mode_labels(session: AsyncSession, levels: Any) -> dict[str, str]:
    """``service_level → label shown to the customer`` for the given levels.

    A line keeps the mode it was paid on even when that route is later
    withdrawn: the routes on offer answer first, then any route that ever
    carried the level, then the key itself (never a blank).
    """
    wanted = {level for level in levels or () if level}
    if not wanted:
        return {}
    labels: dict[str, str] = {}
    for route in await import_routes(session):
        level = route.service_level
        if level and level in wanted and level not in labels:
            labels[level] = route.customer_label or level
    missing = wanted - labels.keys()
    if missing:
        rows = (
            await session.exec(
                select(ShippingRoute)
                .where(col(ShippingRoute.service_level).in_(missing))
                .order_by(
                    col(ShippingRoute.is_active).desc(),
                    col(ShippingRoute.priority).asc(),
                    col(ShippingRoute.id).asc(),
                )
            )
        ).all()
        for row in rows:
            level = getattr(row, "service_level", None)
            if level and level not in labels and row.customer_label:
                labels[level] = row.customer_label
    for level in wanted:
        labels.setdefault(level, level)
    return labels
