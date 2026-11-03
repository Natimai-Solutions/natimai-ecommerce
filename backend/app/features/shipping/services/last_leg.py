"""
Last-leg (zone C) route resolution by customer destination.

Given the customer's destination chain (île → archipel → pays, from the
shipping address' zone), keep only the last-leg routes that serve it and pick
one route per delivery mode:

- ``always_available`` routes (in-store pickup...) match every destination;
- routes with served zones match when one of their zones is in the chain —
  the deeper the zone in the chain, the more specific the match;
- routes with no served zone and not always_available keep the legacy
  behaviour: available everywhere (lets current setups work until the admin
  configures their coverage).

Per delivery mode the most specific match wins, then ``priority`` asc.

Pickup modes are the exception: each pickup point is its own offer. Routes
whose transport mode is ``pickup`` are grouped by delivery mode *and*
destination place, so one « Retrait » mode can list several shops and the
customer picks one (``resolve_last_leg_options``); per mode, the best of them
is still what a checkout without a chosen place gets.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.shipping.models.route import ShippingRoute
from app.features.shipping.models.route_served_place import RouteServedPlace

# Specificity ranks beyond the destination chain (lower = more specific).
_RANK_LEGACY_UNSCOPED_OFFSET = 1  # no served zone configured → everywhere
_RANK_ALWAYS_AVAILABLE_OFFSET = 2  # always_available → everywhere, least specific


PICKUP_TRANSPORT_MODE = "pickup"


@dataclass(frozen=True)
class LastLegCandidate:
    """A last-leg route available for the destination, with its specificity."""

    route: ShippingRoute
    specificity: int

    @property
    def delivery_type(self) -> str:
        return self.route.last_leg_delivery_type or ""

    @property
    def pickup_place_id(self) -> uuid.UUID | None:
        """The pickup point of a pickup route (its destination), else None."""
        if self.route.mode != PICKUP_TRANSPORT_MODE:
            return None
        return self.route.to_place_id


def _offer_key(route: ShippingRoute) -> tuple[str, uuid.UUID | None]:
    """One offer per delivery mode — per pickup point for pickup routes."""
    mode = route.last_leg_delivery_type or ""
    if route.mode == PICKUP_TRANSPORT_MODE:
        return (mode, route.to_place_id)
    return (mode, None)


def _rank(candidate: LastLegCandidate) -> tuple[int, int]:
    return (candidate.specificity, candidate.route.priority or 0)


async def resolve_last_leg_candidates(
    session: AsyncSession,
    destination_chain: list[uuid.UUID],
) -> dict[str, LastLegCandidate]:
    """Best available last-leg route per delivery mode for a destination.

    ``destination_chain`` is ordered nearest-first (île, archipel, pays) and
    may be empty (unknown destination → only always_available and legacy
    unscoped routes are offered). With several pickup points for one mode,
    the most specific (then highest-priority) one stands for the mode.
    """
    best_by_mode: dict[str, LastLegCandidate] = {}
    for candidate in await resolve_last_leg_options(session, destination_chain):
        current = best_by_mode.get(candidate.delivery_type)
        if current is None or _rank(candidate) < _rank(current):
            best_by_mode[candidate.delivery_type] = candidate
    return best_by_mode


async def resolve_last_leg_options(
    session: AsyncSession,
    destination_chain: list[uuid.UUID],
) -> list[LastLegCandidate]:
    """Every offer for a destination: one per delivery mode, one per pickup
    point for pickup modes. Ordered by mode, then specificity and priority.
    """
    routes_result = await session.exec(
        select(ShippingRoute)
        .where(
            col(ShippingRoute.is_to_customer).is_(True),
            col(ShippingRoute.is_active).is_(True),
            col(ShippingRoute.last_leg_delivery_type).is_not(None),
        )
        .order_by(col(ShippingRoute.priority).asc())
    )
    routes = list(routes_result.all())
    if not routes:
        return []

    served_result = await session.exec(
        select(RouteServedPlace).where(
            col(RouteServedPlace.route_id).in_([route.id for route in routes])
        )
    )
    served_by_route: dict[uuid.UUID, set[uuid.UUID]] = {}
    for row in served_result.all():
        served_by_route.setdefault(row.route_id, set()).add(row.place_id)

    chain_rank = {place_id: index for index, place_id in enumerate(destination_chain)}
    chain_length = len(destination_chain)

    best_by_offer: dict[tuple[str, uuid.UUID | None], LastLegCandidate] = {}
    for route in routes:
        if not route.last_leg_delivery_type:
            continue

        served = served_by_route.get(route.id, set())
        specificity: int | None = None
        if served:
            matches = [chain_rank[pid] for pid in served if pid in chain_rank]
            if matches:
                specificity = min(matches)
        elif not route.always_available:
            specificity = chain_length + _RANK_LEGACY_UNSCOPED_OFFSET
        if specificity is None and route.always_available:
            specificity = chain_length + _RANK_ALWAYS_AVAILABLE_OFFSET
        if specificity is None:
            continue  # scoped route that does not serve this destination

        key = _offer_key(route)
        current = best_by_offer.get(key)
        # Routes arrive priority-ordered, so on equal specificity the first wins.
        if current is None or specificity < current.specificity:
            best_by_offer[key] = LastLegCandidate(route=route, specificity=specificity)

    return sorted(
        best_by_offer.values(),
        key=lambda c: (c.delivery_type, *_rank(c), c.route.name),
    )
