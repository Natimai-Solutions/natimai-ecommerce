"""Admin logistics endpoints (superuser).

Phase 4 — logistique avancée. Exposes semantic ship / deliver / consolidate
operations on top of the existing shipping CRUD so the back-office can group
parcels and advance shipment statuses. Each status transition publishes the
`tracking.status_changed` outbox event (→ customer notification email).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlmodel import col, select

from app.api.deps import CurrentSuperUser, SessionDep
from app.core.errors import AppError
from app.features.base.crud import RecordNotFoundError
from app.features.shipping.crud import (
    crud_shipping_route_tracking,
    crud_shipping_route_tracking_consolidation,
    crud_status_definition,
)
from app.features.shipping.models.route_tracking import (
    ShippingRouteTracking,
    ShippingRouteTrackingConsolidation,
    ShippingRouteTrackingConsolidationCreate,
)
from app.features.shipping.models.status import StatusDefinition, StatusDefinitionCreate
from app.outbox.registry import outbox_registry

router = APIRouter(prefix="/admin/shipping", tags=["admin-shipping"])

_ENTITY_TRACKING = "route_tracking"
_ENTITY_CONSOLIDATION = "consolidation"
_CODE_SHIPPED = "shipped"
_CODE_DELIVERED = "delivered"


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class AdminPendingTrackingItem(BaseModel):
    """A tracking segment not yet attached to a consolidation."""

    tracking_id: uuid.UUID
    order_id: uuid.UUID
    route_id: uuid.UUID
    sequence_order: int
    status_code: str | None = None
    status_name: str | None = None
    tracking_ref: str | None = None


class AdminConsolidationItem(BaseModel):
    """A consolidation (parcel grouping)."""

    id: uuid.UUID
    name: str
    consolidation_code: str
    route_id: uuid.UUID
    status_code: str | None = None
    status_name: str | None = None
    total_orders: int
    tracking_ref: str | None = None


class ConsolidationCreateRequest(BaseModel):
    """Create a consolidation for a route."""

    route_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=500)


class AddTrackingsRequest(BaseModel):
    """Bulk-attach trackings to a consolidation."""

    tracking_ids: list[uuid.UUID] = Field(..., min_length=1)


class ShipRequest(BaseModel):
    """Carrier reference for a shipment."""

    tracking_ref: str = Field(..., min_length=1, max_length=100)


class OkResponse(BaseModel):
    """Generic acknowledgement."""

    message: str


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
async def _get_or_create_status(
    session: SessionDep,
    *,
    entity: str,
    code: str,
    name: str,
    is_terminal: bool = False,
) -> StatusDefinition:
    """Resolve a status by code, creating it on demand (statuses aren't seeded)."""
    existing = await crud_status_definition.get_by_code(
        session=session, entity=entity, code=code
    )
    if existing is not None:
        return existing
    return await crud_status_definition.create_draft(
        session=session,
        data=StatusDefinitionCreate(
            entity=entity,
            code=code,
            name=name,
            description=f"Auto-created status for {entity}",
            sequence_order=0,
            is_terminal=is_terminal,
            is_error=False,
            ui_color=None,
            ui_icon=None,
        ),
        user=None,
    )


async def _status_map(session: SessionDep, *, entity: str) -> dict[uuid.UUID, StatusDefinition]:
    defs = await crud_status_definition.get_by_entity(session=session, entity=entity)
    return {s.id: s for s in defs}


async def _publish_tracking_status_changed(
    session: SessionDep,
    *,
    tracking: ShippingRouteTracking,
    status_def: StatusDefinition,
    reason: str | None,
    changed_by: uuid.UUID,
) -> None:
    """Publish the same event the existing update-status route emits."""
    await outbox_registry.publish(
        session=session,
        event_type="tracking.status_changed",
        payload={
            "tracking_id": str(tracking.id),
            "order_id": str(tracking.order_id),
            "status_code": status_def.code,
            "status_name": status_def.name,
            "tracking_ref": tracking.tracking_ref,
            "estimated_delivery": (
                tracking.estimated_delivery.isoformat()
                if tracking.estimated_delivery
                else None
            ),
            "reason": reason,
            "changed_by": str(changed_by),
        },
        correlation_id=tracking.id,
    )


async def _advance_tracking(
    session: SessionDep,
    *,
    tracking_id: uuid.UUID,
    status_def: StatusDefinition,
    admin_id: uuid.UUID,
    tracking_ref: str | None = None,
    reason: str | None = None,
) -> ShippingRouteTracking:
    """Set a tracking's status (forced, no transition-table dependency), stamp the
    carrier ref, and publish the customer notification event."""
    try:
        updated = await crud_shipping_route_tracking.update_status(
            session=session,
            tracking_id=tracking_id,
            new_status_id=status_def.id,
            changed_by=str(admin_id),
            reason=reason,
            force=True,
        )
    except RecordNotFoundError as exc:
        raise AppError(
            code="shipping.tracking.not_found",
            status_code=404,
            message=f"Tracking '{tracking_id}' not found",
            details={"tracking_id": str(tracking_id)},
        ) from exc

    if updated is None:
        raise AppError(
            code="shipping.tracking.not_found",
            status_code=404,
            message=f"Tracking '{tracking_id}' not found",
            details={"tracking_id": str(tracking_id)},
        )

    if tracking_ref is not None:
        updated.tracking_ref = tracking_ref
        session.add(updated)

    await _publish_tracking_status_changed(
        session,
        tracking=updated,
        status_def=status_def,
        reason=reason,
        changed_by=admin_id,
    )
    return updated


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@router.get("/pending-grouping", response_model=list[AdminPendingTrackingItem])
async def list_pending_grouping(
    session: SessionDep,
    _admin: CurrentSuperUser,
) -> list[AdminPendingTrackingItem]:
    """Trackings not yet attached to a consolidation (ready to group)."""
    trackings = await crud_shipping_route_tracking.get_unconsolidated_trackings(
        session=session
    )
    status_by_id = await _status_map(session, entity=_ENTITY_TRACKING)
    items: list[AdminPendingTrackingItem] = []
    for t in trackings:
        status = status_by_id.get(t.status_id)
        items.append(
            AdminPendingTrackingItem(
                tracking_id=t.id,
                order_id=t.order_id,
                route_id=t.route_id,
                sequence_order=t.sequence_order,
                status_code=status.code if status else None,
                status_name=status.name if status else None,
                tracking_ref=t.tracking_ref,
            )
        )
    return items


@router.get("/consolidations", response_model=list[AdminConsolidationItem])
async def list_consolidations(
    session: SessionDep,
    _admin: CurrentSuperUser,
) -> list[AdminConsolidationItem]:
    """All consolidations, newest first."""
    result = await session.exec(
        select(ShippingRouteTrackingConsolidation).order_by(
            col(ShippingRouteTrackingConsolidation.created_at).desc()
        )
    )
    consolidations = list(result.all())
    status_by_id = await _status_map(session, entity=_ENTITY_CONSOLIDATION)
    items: list[AdminConsolidationItem] = []
    for c in consolidations:
        status = status_by_id.get(c.status_id)
        items.append(
            AdminConsolidationItem(
                id=c.id,
                name=c.name,
                consolidation_code=c.consolidation_code,
                route_id=c.route_id,
                status_code=status.code if status else None,
                status_name=status.name if status else None,
                total_orders=c.total_orders,
                tracking_ref=c.tracking_ref,
            )
        )
    return items


@router.post("/consolidations", response_model=AdminConsolidationItem, status_code=201)
async def create_consolidation(
    body: ConsolidationCreateRequest,
    session: SessionDep,
    _admin: CurrentSuperUser,
) -> AdminConsolidationItem:
    """Create an empty consolidation for a route (then attach trackings)."""
    pending_status = await _get_or_create_status(
        session, entity=_ENTITY_CONSOLIDATION, code="pending", name="En attente"
    )
    code = f"CONS-{uuid.uuid4().hex[:8].upper()}"
    consolidation = await crud_shipping_route_tracking_consolidation.create_draft(
        session=session,
        data=ShippingRouteTrackingConsolidationCreate(
            route_id=body.route_id,
            name=body.name,
            consolidation_code=code,
            status_id=pending_status.id,
            tracking_ref=None,
            total_orders=0,
            notes=body.notes,
        ),
        user=None,
    )
    await session.commit()
    await session.refresh(consolidation)
    return AdminConsolidationItem(
        id=consolidation.id,
        name=consolidation.name,
        consolidation_code=consolidation.consolidation_code,
        route_id=consolidation.route_id,
        status_code=pending_status.code,
        status_name=pending_status.name,
        total_orders=consolidation.total_orders,
        tracking_ref=consolidation.tracking_ref,
    )


async def _get_consolidation_or_404(
    session: SessionDep, consolidation_id: uuid.UUID
) -> ShippingRouteTrackingConsolidation:
    try:
        return await crud_shipping_route_tracking_consolidation.read(
            session, id=consolidation_id
        )
    except RecordNotFoundError as exc:
        raise AppError(
            code="shipping.consolidation.not_found",
            status_code=404,
            message=f"Consolidation '{consolidation_id}' not found",
            details={"consolidation_id": str(consolidation_id)},
        ) from exc


@router.post("/consolidations/{consolidation_id}/add-trackings", response_model=OkResponse)
async def add_trackings(
    consolidation_id: uuid.UUID,
    body: AddTrackingsRequest,
    session: SessionDep,
    _admin: CurrentSuperUser,
) -> OkResponse:
    """Bulk-attach trackings to a consolidation."""
    await _get_consolidation_or_404(session, consolidation_id)
    added = 0
    for tracking_id in body.tracking_ids:
        ok = await crud_shipping_route_tracking_consolidation.add_tracking_to_consolidation(
            session=session,
            consolidation_id=consolidation_id,
            tracking_id=tracking_id,
        )
        if ok:
            added += 1
    await session.commit()
    return OkResponse(message=f"{added} tracking(s) ajouté(s) à la consolidation")


@router.post("/consolidations/{consolidation_id}/ship-all", response_model=OkResponse)
async def ship_consolidation(
    consolidation_id: uuid.UUID,
    body: ShipRequest,
    session: SessionDep,
    admin: CurrentSuperUser,
) -> OkResponse:
    """Mark all trackings of a consolidation as shipped and stamp the carrier ref."""
    consolidation = await _get_consolidation_or_404(session, consolidation_id)

    shipped_tracking = await _get_or_create_status(
        session, entity=_ENTITY_TRACKING, code=_CODE_SHIPPED, name="Expédiée"
    )
    shipped_consolidation = await _get_or_create_status(
        session, entity=_ENTITY_CONSOLIDATION, code=_CODE_SHIPPED, name="Expédiée"
    )

    trackings = await crud_shipping_route_tracking.get_trackings_for_consolidation(
        session=session, consolidation_id=consolidation_id
    )
    for t in trackings:
        await _advance_tracking(
            session,
            tracking_id=t.id,
            status_def=shipped_tracking,
            admin_id=admin.id,
            tracking_ref=body.tracking_ref,
        )

    consolidation.status_id = shipped_consolidation.id
    consolidation.tracking_ref = body.tracking_ref
    session.add(consolidation)
    await session.commit()
    return OkResponse(
        message=f"{len(trackings)} tracking(s) marqué(s) expédié(s)",
    )


@router.post("/trackings/{tracking_id}/ship", response_model=OkResponse)
async def ship_tracking(
    tracking_id: uuid.UUID,
    body: ShipRequest,
    session: SessionDep,
    admin: CurrentSuperUser,
) -> OkResponse:
    """Mark a single tracking as shipped (requires the carrier reference)."""
    shipped = await _get_or_create_status(
        session, entity=_ENTITY_TRACKING, code=_CODE_SHIPPED, name="Expédiée"
    )
    await _advance_tracking(
        session,
        tracking_id=tracking_id,
        status_def=shipped,
        admin_id=admin.id,
        tracking_ref=body.tracking_ref,
    )
    await session.commit()
    return OkResponse(message="Tracking marqué expédié")


@router.post("/trackings/{tracking_id}/deliver", response_model=OkResponse)
async def deliver_tracking(
    tracking_id: uuid.UUID,
    session: SessionDep,
    admin: CurrentSuperUser,
) -> OkResponse:
    """Mark a single tracking as delivered (terminal)."""
    delivered = await _get_or_create_status(
        session,
        entity=_ENTITY_TRACKING,
        code=_CODE_DELIVERED,
        name="Livrée",
        is_terminal=True,
    )
    await _advance_tracking(
        session,
        tracking_id=tracking_id,
        status_def=delivered,
        admin_id=admin.id,
    )
    await session.commit()
    return OkResponse(message="Tracking marqué livré")
