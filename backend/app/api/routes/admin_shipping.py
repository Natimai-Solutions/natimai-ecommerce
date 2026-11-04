"""Admin logistics endpoints (superuser).

Phase 4 — logistique avancée. Exposes semantic ship / deliver / consolidate
operations on top of the existing shipping CRUD so the back-office can group
parcels and advance shipment statuses. Each status transition publishes the
`tracking.status_changed` outbox event (→ customer notification email).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlmodel import col, func, select

from app.api.deps import CurrentLogisticsAdmin, SessionDep
from app.core.errors import AppError
from app.features.base.crud import RecordNotFoundError
from app.features.shipping.crud import (
    crud_shipping_route_tracking,
    crud_shipping_route_tracking_consolidation,
    crud_status_definition,
)
from app.features.shipping.models.carrier import Carrier, CarrierPublic
from app.features.shipping.models.route import ShippingRoute
from app.features.shipping.models.route_tracking import (
    ShippingRouteTracking,
    ShippingRouteTrackingConsolidation,
    ShippingRouteTrackingConsolidationCreate,
)
from app.features.shipping.models.status import StatusDefinition, StatusDefinitionCreate
from app.features.shipping.services.tracking_url import (
    carrier_tracking_url,
    validate_tracking_url_template,
)
from app.outbox.registry import outbox_registry

router = APIRouter(prefix="/admin/shipping", tags=["admin-shipping"])

_ENTITY_TRACKING = "route_tracking"
_ENTITY_CONSOLIDATION = "consolidation"
_CODE_SHIPPED = "shipped"
_CODE_DELIVERED = "delivered"
_CODE_IN_PROGRESS = "in_progress"


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
    is_final_leg: bool = Field(
        default=False,
        description=(
            "Last leg of the order's journey (customer delivery route or highest "
            "sequence) — close it with « Livrer », not « Tronçon suivant »."
        ),
    )


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
    """Carrier + reference for a shipment (both optional — may be self-managed)."""

    tracking_ref: str | None = Field(default=None, max_length=100)
    carrier_id: uuid.UUID | None = None


class AdvanceConsolidationRequest(BaseModel):
    """Advance a consolidation. ``ungroup=True`` detaches each parcel first so it
    continues individually on its own next leg."""

    ungroup: bool = False


class UngroupHintResponse(BaseModel):
    """Smart default for the « garder / dégrouper » popup."""

    suggest_ungroup: bool


class OkResponse(BaseModel):
    """Generic acknowledgement."""

    message: str


class AdvanceResponse(BaseModel):
    """Result of advancing a parcel to the next leg of its journey."""

    has_next: bool
    next_tracking_id: uuid.UUID | None = None
    message: str


class AdminJourneyLeg(BaseModel):
    """One leg (tronçon) of an order's multi-hop journey, with resolved names."""

    tracking_id: uuid.UUID
    sequence_order: int
    route_name: str | None
    from_place: str | None
    to_place: str | None
    mode: str | None
    status_code: str | None
    status_name: str | None
    tracking_ref: str | None
    is_current: bool
    # Carrier hand-over (None = self-managed) + the customer's tracking link.
    carrier_id: uuid.UUID | None = None
    carrier_name: str | None = None
    tracking_url: str | None = None
    # Drives the order page's actions: the final leg closes with « Livrer »,
    # a terminal leg has no action left.
    is_final_leg: bool = False
    is_terminal: bool = False


class CarrierWriteRequest(BaseModel):
    """Create / replace a carrier (admin « Transporteurs » page)."""

    name: str = Field(..., min_length=1, max_length=100)
    code: str = Field(..., min_length=1, max_length=50)
    tracking_url_template: str | None = Field(default=None, max_length=500)


class CarrierPatchRequest(BaseModel):
    """Partial carrier update; ``is_active=False`` retires it from the selector."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    code: str | None = Field(default=None, min_length=1, max_length=50)
    tracking_url_template: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None


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


async def _status_map(
    session: SessionDep, *, entity: str
) -> dict[uuid.UUID, StatusDefinition]:
    defs = await crud_status_definition.get_by_entity(session=session, entity=entity)
    return {s.id: s for s in defs}


async def _publish_tracking_status_changed(
    session: SessionDep,
    *,
    tracking: ShippingRouteTracking,
    status_code: str,
    status_name: str,
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
            "status_code": status_code,
            "status_name": status_name,
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
    status_id: uuid.UUID,
    status_code: str,
    status_name: str,
    admin_id: uuid.UUID,
    tracking_ref: str | None = None,
    carrier_id: uuid.UUID | None = None,
    reason: str | None = None,
) -> ShippingRouteTracking:
    """Set a tracking's status (forced, no transition-table dependency), stamp the
    carrier ref, and publish the customer notification event.

    Status fields are passed as plain values (not the ORM ``StatusDefinition``):
    ``update_status`` commits internally, which would expire a shared status
    instance and make a later ``.code``/``.id`` access raise MissingGreenlet —
    fatal in a ship-all loop where the same status is reused for every tracking.
    """
    try:
        updated = await crud_shipping_route_tracking.update_status(
            session=session,
            tracking_id=tracking_id,
            new_status_id=status_id,
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

    if tracking_ref:
        updated.tracking_ref = tracking_ref
    if carrier_id is not None:
        updated.carrier_id = carrier_id
    if tracking_ref or carrier_id is not None:
        session.add(updated)

    await _publish_tracking_status_changed(
        session,
        tracking=updated,
        status_code=status_code,
        status_name=status_name,
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
    _admin: CurrentLogisticsAdmin,
) -> list[AdminPendingTrackingItem]:
    """Trackings not yet attached to a consolidation (ready to group)."""
    trackings = await crud_shipping_route_tracking.get_unconsolidated_trackings(
        session=session
    )
    status_by_id = await _status_map(session, entity=_ENTITY_TRACKING)

    # Final-leg detection: customer-delivery route (is_to_customer) or highest
    # sequence of the order's journey. The UI closes those with « Livrer ».
    last_leg_route_ids: set[uuid.UUID] = set()
    max_sequence_by_order: dict[uuid.UUID, int] = {}
    if trackings:
        route_rows = await session.exec(
            select(ShippingRoute.id).where(
                col(ShippingRoute.id).in_({t.route_id for t in trackings}),
                col(ShippingRoute.is_to_customer).is_(True),
            )
        )
        last_leg_route_ids = set(route_rows.all())
        sequence_rows = await session.exec(
            select(
                ShippingRouteTracking.order_id,
                func.max(ShippingRouteTracking.sequence_order),
            )
            .where(
                col(ShippingRouteTracking.order_id).in_({t.order_id for t in trackings})
            )
            .group_by(col(ShippingRouteTracking.order_id))
        )
        max_sequence_by_order = {row[0]: row[1] for row in sequence_rows.all()}

    items: list[AdminPendingTrackingItem] = []
    for t in trackings:
        status = status_by_id.get(t.status_id)
        is_final = t.route_id in last_leg_route_ids or (
            t.sequence_order >= max_sequence_by_order.get(t.order_id, t.sequence_order)
        )
        items.append(
            AdminPendingTrackingItem(
                tracking_id=t.id,
                order_id=t.order_id,
                route_id=t.route_id,
                sequence_order=t.sequence_order,
                status_code=status.code if status else None,
                status_name=status.name if status else None,
                tracking_ref=t.tracking_ref,
                is_final_leg=is_final,
            )
        )
    return items


@router.get("/consolidations", response_model=list[AdminConsolidationItem])
async def list_consolidations(
    session: SessionDep,
    _admin: CurrentLogisticsAdmin,
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


@router.get("/carriers", response_model=list[CarrierPublic])
async def list_carriers(
    session: SessionDep,
    _admin: CurrentLogisticsAdmin,
    include_inactive: bool = Query(
        default=False,
        description="Also return retired carriers (management page).",
    ),
) -> list[CarrierPublic]:
    """Carriers for the « remise au transporteur » selector (active only by
    default) and the management page."""
    statement = select(Carrier).order_by(col(Carrier.name).asc())
    if not include_inactive:
        statement = statement.where(col(Carrier.is_active).is_(True))
    result = await session.exec(statement)
    return [CarrierPublic.model_validate(c) for c in result.all()]


def _normalize_carrier_code(code: str) -> str:
    """Stable slug: lower-case, dashes/spaces → underscore."""
    cleaned = code.strip().lower().replace("-", "_").replace(" ", "_")
    if not cleaned:
        raise AppError(
            code="carrier.code.invalid",
            status_code=400,
            message="Le code du transporteur est requis",
        )
    return cleaned


def _validated_template(template: str | None) -> str | None:
    try:
        return validate_tracking_url_template(template)
    except ValueError as exc:
        raise AppError(
            code="carrier.tracking_url_template.invalid",
            status_code=400,
            message=str(exc),
            details={"tracking_url_template": template},
        ) from exc


async def _ensure_carrier_code_free(
    session: SessionDep, *, code: str, exclude_id: uuid.UUID | None = None
) -> None:
    statement = select(Carrier).where(col(Carrier.code) == code)
    if exclude_id is not None:
        statement = statement.where(col(Carrier.id) != exclude_id)
    existing = (await session.exec(statement)).first()
    if existing is not None:
        raise AppError(
            code="carrier.code.duplicate",
            status_code=409,
            message=f"Un transporteur porte déjà le code '{code}'",
            details={"code": code, "carrier_id": str(existing.id)},
        )


async def _get_carrier_or_404(session: SessionDep, carrier_id: uuid.UUID) -> Carrier:
    carrier = (
        await session.exec(select(Carrier).where(col(Carrier.id) == carrier_id))
    ).first()
    if carrier is None:
        raise AppError(
            code="carrier.not_found",
            status_code=404,
            message=f"Transporteur '{carrier_id}' introuvable",
            details={"carrier_id": str(carrier_id)},
        )
    return carrier


@router.post("/carriers", response_model=CarrierPublic, status_code=201)
async def create_carrier(
    body: CarrierWriteRequest,
    session: SessionDep,
    admin: CurrentLogisticsAdmin,
) -> CarrierPublic:
    """Add a carrier (DHL, Chronopost, a local courier…) with its tracking-link
    template. No carrier API: the reference is typed at hand-over."""
    code = _normalize_carrier_code(body.code)
    await _ensure_carrier_code_free(session, code=code)
    carrier = Carrier(
        name=body.name.strip(),
        code=code,
        tracking_url_template=_validated_template(body.tracking_url_template),
        created_by_id=admin.id,
    )
    session.add(carrier)
    await session.commit()
    await session.refresh(carrier)
    return CarrierPublic.model_validate(carrier)


@router.patch("/carriers/{carrier_id}", response_model=CarrierPublic)
async def update_carrier(
    carrier_id: uuid.UUID,
    body: CarrierPatchRequest,
    session: SessionDep,
    _admin: CurrentLogisticsAdmin,
) -> CarrierPublic:
    """Rename a carrier, fix its tracking template, or retire / restore it."""
    carrier = await _get_carrier_or_404(session, carrier_id)
    fields = body.model_dump(exclude_unset=True)
    if "code" in fields and fields["code"] is not None:
        code = _normalize_carrier_code(fields["code"])
        await _ensure_carrier_code_free(session, code=code, exclude_id=carrier.id)
        carrier.code = code
    if "name" in fields and fields["name"] is not None:
        carrier.name = fields["name"].strip()
    if "tracking_url_template" in fields:
        carrier.tracking_url_template = _validated_template(
            fields["tracking_url_template"]
        )
    if "is_active" in fields and fields["is_active"] is not None:
        carrier.is_active = fields["is_active"]
    session.add(carrier)
    await session.commit()
    await session.refresh(carrier)
    return CarrierPublic.model_validate(carrier)


@router.delete("/carriers/{carrier_id}", response_model=OkResponse)
async def retire_carrier(
    carrier_id: uuid.UUID,
    session: SessionDep,
    _admin: CurrentLogisticsAdmin,
) -> OkResponse:
    """Retire a carrier (soft): past shipments keep their carrier and link."""
    carrier = await _get_carrier_or_404(session, carrier_id)
    carrier.is_active = False
    session.add(carrier)
    await session.commit()
    return OkResponse(message="Transporteur retiré du sélecteur")


@router.post("/consolidations", response_model=AdminConsolidationItem, status_code=201)
async def create_consolidation(
    body: ConsolidationCreateRequest,
    session: SessionDep,
    _admin: CurrentLogisticsAdmin,
) -> AdminConsolidationItem:
    """Create an empty consolidation for a route (then attach trackings)."""
    consolidation, pending_status = await _new_consolidation(
        session, route_id=body.route_id, name=body.name, notes=body.notes
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


async def _new_consolidation(
    session: SessionDep,
    *,
    route_id: uuid.UUID,
    name: str,
    notes: str | None,
) -> tuple[ShippingRouteTrackingConsolidation, StatusDefinition]:
    """An empty « En attente » consolidation with a fresh code (no commit)."""
    pending_status = await _get_or_create_status(
        session, entity=_ENTITY_CONSOLIDATION, code="pending", name="En attente"
    )
    code = f"CONS-{uuid.uuid4().hex[:8].upper()}"
    consolidation = await crud_shipping_route_tracking_consolidation.create_draft(
        session=session,
        data=ShippingRouteTrackingConsolidationCreate(
            route_id=route_id,
            name=name,
            consolidation_code=code,
            status_id=pending_status.id,
            tracking_ref=None,
            total_orders=0,
            notes=notes,
        ),
        user=None,
    )
    return consolidation, pending_status


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


@router.post(
    "/consolidations/{consolidation_id}/add-trackings", response_model=OkResponse
)
async def add_trackings(
    consolidation_id: uuid.UUID,
    body: AddTrackingsRequest,
    session: SessionDep,
    _admin: CurrentLogisticsAdmin,
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
    admin: CurrentLogisticsAdmin,
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
    # Capture everything as plain values BEFORE the loop: each _advance_tracking
    # commits, which expires the shared status instances and the tracking rows —
    # re-reading their attributes afterwards would raise MissingGreenlet.
    tracking_ids = [t.id for t in trackings]
    shipped_status_id = shipped_tracking.id
    shipped_status_code = shipped_tracking.code
    shipped_status_name = shipped_tracking.name
    consolidation_status_id = shipped_consolidation.id
    # admin is the CurrentLogisticsAdmin ORM instance — it is also expired by the
    # per-tracking commits below, so capture its id before the loop.
    admin_id = admin.id

    for tid in tracking_ids:
        await _advance_tracking(
            session,
            tracking_id=tid,
            status_id=shipped_status_id,
            status_code=shipped_status_code,
            status_name=shipped_status_name,
            admin_id=admin_id,
            tracking_ref=body.tracking_ref,
            carrier_id=body.carrier_id,
        )

    consolidation.status_id = consolidation_status_id
    if body.tracking_ref:
        consolidation.tracking_ref = body.tracking_ref
    if body.carrier_id is not None:
        consolidation.carrier_id = body.carrier_id
    session.add(consolidation)
    await session.commit()
    return OkResponse(
        message=f"{len(tracking_ids)} tracking(s) marqué(s) expédié(s)",
    )


@router.post("/trackings/{tracking_id}/ship", response_model=OkResponse)
async def ship_tracking(
    tracking_id: uuid.UUID,
    body: ShipRequest,
    session: SessionDep,
    admin: CurrentLogisticsAdmin,
) -> OkResponse:
    """Mark a single tracking as shipped (carrier reference optional)."""
    shipped = await _get_or_create_status(
        session, entity=_ENTITY_TRACKING, code=_CODE_SHIPPED, name="Expédiée"
    )
    await _advance_tracking(
        session,
        tracking_id=tracking_id,
        status_id=shipped.id,
        status_code=shipped.code,
        status_name=shipped.name,
        admin_id=admin.id,
        tracking_ref=body.tracking_ref,
        carrier_id=body.carrier_id,
    )
    await session.commit()
    return OkResponse(message="Tracking marqué expédié")


@router.post("/trackings/{tracking_id}/deliver", response_model=OkResponse)
async def deliver_tracking(
    tracking_id: uuid.UUID,
    session: SessionDep,
    admin: CurrentLogisticsAdmin,
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
        status_id=delivered.id,
        status_code=delivered.code,
        status_name=delivered.name,
        admin_id=admin.id,
    )
    await session.commit()
    return OkResponse(message="Tracking marqué livré")


@router.post("/trackings/{tracking_id}/advance", response_model=AdvanceResponse)
async def advance_tracking(
    tracking_id: uuid.UUID,
    session: SessionDep,
    admin: CurrentLogisticsAdmin,
) -> AdvanceResponse:
    """Complete this leg (tronçon) and activate the next one in the order's
    multi-hop journey. ``activate_next_route`` commits internally."""
    admin_id = admin.id  # captured: the progression commits expire `admin`

    tracking = await session.get(ShippingRouteTracking, tracking_id)
    if tracking is None:
        raise AppError(
            code="shipping.tracking.not_found",
            status_code=404,
            message="Tracking not found",
            details={"tracking_id": str(tracking_id)},
        )
    # A customer-delivery leg has no « next »: advancing it would mark it
    # `completed` (terminal) and the delivery could never be confirmed.
    route = await session.get(ShippingRoute, tracking.route_id)
    if route is not None and route.is_to_customer:
        raise AppError(
            code="shipping.advance.last_leg",
            status_code=400,
            message=(
                "Dernier tronçon (livraison client) — utilisez « Livrer » "
                "pour confirmer la livraison"
            ),
            details={"tracking_id": str(tracking_id), "route_id": str(route.id)},
        )

    next_tracking = await crud_shipping_route_tracking.activate_next_route(
        session=session,
        current_tracking_id=tracking_id,
        changed_by=admin_id,
    )
    if next_tracking is None:
        return AdvanceResponse(
            has_next=False, message="Dernier tronçon — parcours terminé"
        )
    # Notify the customer the parcel moved on to the next leg. Snapshot the id
    # before the commit, which expires next_tracking.
    next_id = next_tracking.id
    await _publish_tracking_status_changed(
        session,
        tracking=next_tracking,
        status_code=_CODE_IN_PROGRESS,
        status_name="En cours",
        reason="Passage au tronçon suivant",
        changed_by=admin_id,
    )
    await session.commit()
    return AdvanceResponse(
        has_next=True,
        next_tracking_id=next_id,
        message="Tronçon suivant activé",
    )


@router.post(
    "/consolidations/{consolidation_id}/advance-all", response_model=OkResponse
)
async def advance_consolidation(
    consolidation_id: uuid.UUID,
    body: AdvanceConsolidationRequest,
    session: SessionDep,
    admin: CurrentLogisticsAdmin,
) -> OkResponse:
    """Advance every parcel of a consolidation to its next leg.

    ``ungroup=True`` first detaches each parcel from the consolidation, so it
    continues individually (e.g. into its own last-leg delivery).

    Otherwise the grouping is kept for the next leg: when the parcels' next
    legs share one route, they are attached to a new consolidation on that
    route (the finished legs stay in this one, for the record). Next legs on
    different routes cannot travel together and continue individually.
    """
    current = await _get_consolidation_or_404(session, consolidation_id)
    lot_name, lot_notes = current.name, current.notes
    trackings = await crud_shipping_route_tracking.get_trackings_for_consolidation(
        session=session, consolidation_id=consolidation_id
    )
    # Capture before the loop: each activate_next_route commits and expires the
    # tracking rows and the admin user (MissingGreenlet otherwise).
    tracking_ids = [t.id for t in trackings]
    admin_id = admin.id

    advanced = 0
    # (next tracking id, its route) — read right away: the next iteration's
    # commit expires the row.
    next_legs: list[tuple[uuid.UUID, uuid.UUID]] = []
    for tid in tracking_ids:
        if body.ungroup:
            await crud_shipping_route_tracking_consolidation.remove_tracking_from_consolidation(
                session=session, tracking_id=tid
            )
        next_tracking = await crud_shipping_route_tracking.activate_next_route(
            session=session,
            current_tracking_id=tid,
            changed_by=admin_id,
        )
        if next_tracking is not None:
            advanced += 1
            next_legs.append((next_tracking.id, next_tracking.route_id))
            # Notify the customer; read next_tracking now (this iteration's
            # activate_next_route refreshed it, the next one will expire it).
            await _publish_tracking_status_changed(
                session,
                tracking=next_tracking,
                status_code=_CODE_IN_PROGRESS,
                status_name="En cours",
                reason="Passage au tronçon suivant (lot)",
                changed_by=admin_id,
            )

    message = f"{advanced}/{len(tracking_ids)} colis passé(s) au tronçon suivant"
    regrouped = await _regroup_next_legs(
        session,
        next_legs=[] if body.ungroup else next_legs,
        name=lot_name,
        notes=lot_notes,
    )
    if regrouped is not None:
        message += f", regroupés dans {regrouped}"
    elif not body.ungroup and len(next_legs) > 1:
        message += " ; trajets suivants différents : colis non regroupés"
    await session.commit()
    return OkResponse(message=message)


async def _regroup_next_legs(
    session: SessionDep,
    *,
    next_legs: list[tuple[uuid.UUID, uuid.UUID]],
    name: str,
    notes: str | None,
) -> str | None:
    """Keep a lot together on its next leg: a new consolidation on the next
    legs' common route, holding them. Returns its code, or ``None`` when there
    is nothing to group or the next legs do not share a route."""
    routes = {route_id for _, route_id in next_legs}
    if not next_legs or len(routes) != 1:
        return None
    consolidation, _ = await _new_consolidation(
        session, route_id=routes.pop(), name=name, notes=notes
    )
    code = consolidation.consolidation_code
    consolidation_id = consolidation.id
    for tracking_id, _route in next_legs:
        await crud_shipping_route_tracking_consolidation.add_tracking_to_consolidation(
            session=session,
            consolidation_id=consolidation_id,
            tracking_id=tracking_id,
        )
    return code


@router.post(
    "/consolidations/{consolidation_id}/deliver-all", response_model=OkResponse
)
async def deliver_consolidation(
    consolidation_id: uuid.UUID,
    session: SessionDep,
    admin: CurrentLogisticsAdmin,
) -> OkResponse:
    """Deliver every parcel of a consolidation.

    Delivery is always individual, so each parcel is detached from the lot
    (forced ungroup) and marked delivered (terminal).
    """
    await _get_consolidation_or_404(session, consolidation_id)
    delivered = await _get_or_create_status(
        session,
        entity=_ENTITY_TRACKING,
        code=_CODE_DELIVERED,
        name="Livrée",
        is_terminal=True,
    )
    delivered_consolidation = await _get_or_create_status(
        session,
        entity=_ENTITY_CONSOLIDATION,
        code=_CODE_DELIVERED,
        name="Livrée",
        is_terminal=True,
    )
    trackings = await crud_shipping_route_tracking.get_trackings_for_consolidation(
        session=session, consolidation_id=consolidation_id
    )
    # Capture before the per-tracking commits (MissingGreenlet otherwise).
    tracking_ids = [t.id for t in trackings]
    delivered_status_id = delivered.id
    delivered_status_code = delivered.code
    delivered_status_name = delivered.name
    consolidation_status_id = delivered_consolidation.id
    admin_id = admin.id

    for tid in tracking_ids:
        await crud_shipping_route_tracking_consolidation.remove_tracking_from_consolidation(
            session=session, tracking_id=tid
        )
        await _advance_tracking(
            session,
            tracking_id=tid,
            status_id=delivered_status_id,
            status_code=delivered_status_code,
            status_name=delivered_status_name,
            admin_id=admin_id,
        )

    # The (now empty) consolidation is marked delivered too. Re-fetch: the loop's
    # commits above expired the instance.
    consolidation = await session.get(
        ShippingRouteTrackingConsolidation, consolidation_id
    )
    if consolidation is not None:
        consolidation.status_id = consolidation_status_id
        session.add(consolidation)
    await session.commit()
    return OkResponse(message=f"{len(tracking_ids)} colis dégroupé(s) et livré(s)")


@router.get(
    "/consolidations/{consolidation_id}/ungroup-hint",
    response_model=UngroupHintResponse,
)
async def consolidation_ungroup_hint(
    consolidation_id: uuid.UUID,
    session: SessionDep,
    _admin: CurrentLogisticsAdmin,
) -> UngroupHintResponse:
    """Smart default for the « garder / dégrouper » popup."""
    await _get_consolidation_or_404(session, consolidation_id)
    suggest = await crud_shipping_route_tracking.suggest_ungroup_for_consolidation(
        session=session, consolidation_id=consolidation_id
    )
    return UngroupHintResponse(suggest_ungroup=suggest)


@router.get("/orders/{order_id}/journey", response_model=list[AdminJourneyLeg])
async def order_journey(
    order_id: uuid.UUID,
    session: SessionDep,
    _admin: CurrentLogisticsAdmin,
) -> list[AdminJourneyLeg]:
    """Ordered legs (tronçons 1..N) of an order's journey, with resolved status
    and place names — feeds the admin « parcours du colis » timeline."""
    trackings = await crud_shipping_route_tracking.get_trackings_by_order_sequence(
        session=session, order_id=order_id
    )
    if not trackings:
        raise AppError(
            code="order.not_found",
            status_code=404,
            message=f"Aucun tronçon pour la commande '{order_id}'",
            details={"order_id": str(order_id)},
        )

    status_by_id = await _status_map(session, entity=_ENTITY_TRACKING)
    route_ids = {t.route_id for t in trackings}
    routes_result = await session.exec(
        select(ShippingRoute).where(col(ShippingRoute.id).in_(route_ids))
    )
    route_by_id = {r.id: r for r in routes_result.all()}

    # Current leg = first non-terminal one by sequence.
    current_id: uuid.UUID | None = None
    for t in trackings:
        st = status_by_id.get(t.status_id)
        if st is None or not st.is_terminal:
            current_id = t.id
            break

    max_sequence = max(t.sequence_order for t in trackings)
    carrier_ids = {t.carrier_id for t in trackings if t.carrier_id is not None}
    carrier_by_id: dict[uuid.UUID, Carrier] = {}
    if carrier_ids:
        carriers_result = await session.exec(
            select(Carrier).where(col(Carrier.id).in_(carrier_ids))
        )
        carrier_by_id = {c.id: c for c in carriers_result.all()}

    legs: list[AdminJourneyLeg] = []
    for t in trackings:
        st = status_by_id.get(t.status_id)
        route = route_by_id.get(t.route_id)
        carrier = carrier_by_id.get(t.carrier_id) if t.carrier_id else None
        legs.append(
            AdminJourneyLeg(
                tracking_id=t.id,
                sequence_order=t.sequence_order,
                route_name=route.name if route else None,
                from_place=route.from_place.name
                if route and route.from_place
                else None,
                to_place=route.to_place.name if route and route.to_place else None,
                mode=route.mode if route else None,
                status_code=st.code if st else None,
                status_name=st.name if st else None,
                tracking_ref=t.tracking_ref,
                is_current=(t.id == current_id),
                carrier_id=carrier.id if carrier else None,
                carrier_name=carrier.name if carrier else None,
                tracking_url=carrier_tracking_url(
                    carrier.tracking_url_template if carrier else None,
                    t.tracking_ref,
                ),
                is_final_leg=bool(route and route.is_to_customer)
                or t.sequence_order >= max_sequence,
                is_terminal=bool(st is not None and st.is_terminal),
            )
        )
    return legs
