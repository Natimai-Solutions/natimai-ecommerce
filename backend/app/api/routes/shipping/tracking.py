# mypy: disable-error-code="arg-type,call-arg,misc,no-untyped-def,var-annotated"

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from sqlmodel import Field, SQLModel

from app.api.base_router import BaseRouter
from app.api.deps import CurrentSuperUser, SessionDep
from app.features.base.crud import RecordNotFoundError
from app.features.shipping.crud import (
    crud_shipping_route_tracking,
    crud_shipping_route_tracking_consolidation,
    crud_status_definition,
)
from app.features.shipping.models.route_tracking import (
    ShippingRouteTracking,
    ShippingRouteTrackingConsolidationCreate,
    ShippingRouteTrackingConsolidationPublic,
    ShippingRouteTrackingConsolidationsPublic,
    ShippingRouteTrackingConsolidationUpdate,
    ShippingRouteTrackingCreate,
    ShippingRouteTrackingLogsPublic,
    ShippingRouteTrackingPublic,
    ShippingRouteTrackingsPublic,
    ShippingRouteTrackingUpdate,
)
from app.features.shipping.models.status import StatusDefinition

_SUPPLIER_DELAY_STATUS_CODES = {
    "supplier_delay",
    "supplier_delayed",
    "delayed_supplier",
    "retard_fournisseur",
}
_SEGMENT_FAILURE_STATUS_CODES = {
    "segment_failed",
    "segment_failure",
    "failed",
    "echec_segment",
}
_SPLIT_PARCEL_NOTE_MARKERS = (
    "split_parcel",
    "split_colis",
    "colis_split",
    "multi_colis",
)


def _normalize_text(value: str | None) -> str:
    """Normalize optional text for case-insensitive comparisons."""
    if value is None:
        return ""
    return value.strip().lower()


def _is_supplier_delay_status_code(code: str) -> bool:
    """Return whether a status code represents supplier delay."""
    normalized_code = _normalize_text(code)
    if normalized_code in _SUPPLIER_DELAY_STATUS_CODES:
        return True
    return "supplier" in normalized_code and "delay" in normalized_code


def _is_segment_failure_status_code(code: str) -> bool:
    """Return whether a status code represents segment failure."""
    normalized_code = _normalize_text(code)
    if normalized_code in _SEGMENT_FAILURE_STATUS_CODES:
        return True
    return normalized_code.endswith("_failed")


def _derive_order_overall_status(
    trackings: list[ShippingRouteTracking],
    *,
    status_by_id: dict[uuid.UUID, StatusDefinition],
) -> tuple[int | None, str]:
    """Derive the current sequence and overall order status from tracking segments."""
    if not trackings:
        return None, "unknown"

    ordered_trackings = sorted(trackings, key=lambda tracking: tracking.sequence_order)
    resolved_statuses: list[tuple[ShippingRouteTracking, StatusDefinition]] = []

    for tracking in ordered_trackings:
        status_definition = status_by_id.get(tracking.status_id)
        if status_definition is None:
            continue
        resolved_statuses.append((tracking, status_definition))

    if not resolved_statuses:
        return ordered_trackings[-1].sequence_order, "unknown"

    for tracking, status_definition in resolved_statuses:
        if status_definition.is_error:
            return tracking.sequence_order, status_definition.code

    for tracking, status_definition in resolved_statuses:
        if not status_definition.is_terminal:
            return tracking.sequence_order, status_definition.code

    last_tracking, last_status_definition = resolved_statuses[-1]
    return last_tracking.sequence_order, last_status_definition.code


def _derive_order_exception_scenarios(
    trackings: list[ShippingRouteTracking],
    *,
    status_by_id: dict[uuid.UUID, StatusDefinition],
) -> list[str]:
    """Derive exception scenarios for an order from tracking segments."""
    if not trackings:
        return []

    has_supplier_delay = False
    has_segment_failure = False
    has_split_parcel = False

    sequence_counts: dict[int, int] = {}

    for tracking in sorted(trackings, key=lambda item: item.sequence_order):
        sequence_counts[tracking.sequence_order] = (
            sequence_counts.get(tracking.sequence_order, 0) + 1
        )

        status_definition = status_by_id.get(tracking.status_id)
        status_code = _normalize_text(
            status_definition.code if status_definition else None
        )
        notes_text = _normalize_text(tracking.notes)

        is_supplier_delay = _is_supplier_delay_status_code(status_code)
        if is_supplier_delay:
            has_supplier_delay = True

        if _is_segment_failure_status_code(status_code):
            has_segment_failure = True
        elif status_definition and status_definition.is_error and not is_supplier_delay:
            has_segment_failure = True

        if any(marker in notes_text for marker in _SPLIT_PARCEL_NOTE_MARKERS):
            has_split_parcel = True

    if any(count > 1 for count in sequence_counts.values()):
        has_split_parcel = True

    scenarios: list[str] = []
    if has_supplier_delay:
        scenarios.append("supplier_delay")
    if has_split_parcel:
        scenarios.append("parcel_split")
    if has_segment_failure:
        scenarios.append("segment_failure")

    return scenarios


# Modèles de requête pour les endpoints POST
class UpdateStatusRequest(SQLModel):
    """Request payload for updating tracking status."""

    new_status_id: uuid.UUID = Field(description="Nouveau statut")
    reason: str | None = Field(default=None, description="Raison du changement")


# Modèles de réponse pour les endpoints spécialisés
class TrackingStatusResponse(SQLModel):
    """Current status snapshot for a tracking record."""

    tracking_id: uuid.UUID = Field(description="ID du tracking")
    order_id: uuid.UUID = Field(description="ID de la commande")
    current_status: str = Field(description="Statut actuel")
    current_status_name: str = Field(description="Nom du statut actuel")
    sequence_order: int = Field(description="Ordre dans la séquence")
    estimated_arrival: str | None = Field(default=None, description="Arrivée estimée")
    tracking_ref: str | None = Field(default=None, description="Référence de suivi")


class TrackingHistoryResponse(SQLModel):
    """Historical status changes for a tracking record."""

    tracking_id: uuid.UUID = Field(description="ID du tracking")
    history: list[ShippingRouteTrackingLogsPublic] = Field(
        description="Historique des changements de statut"
    )
    total_changes: int = Field(description="Nombre total de changements")


class OrderTrackingResponse(SQLModel):
    """Aggregated tracking view for an order."""

    order_id: uuid.UUID = Field(description="ID de la commande")
    trackings: list[ShippingRouteTrackingPublic] = Field(
        description="Liste des trackings pour cette commande"
    )
    current_route_sequence: int | None = Field(
        default=None, description="Séquence de route actuelle"
    )
    overall_status: str = Field(description="Statut global de la commande")
    exception_scenarios: list[str] = Field(
        default_factory=list,
        description="Scenarios d'exception detectes pour la commande",
    )
    consolidations: list[ShippingRouteTrackingConsolidationPublic] = Field(
        default_factory=list, description="Consolidations associées"
    )


class ShippingRouteTrackingRouter(
    BaseRouter[
        ShippingRouteTracking,
        ShippingRouteTrackingCreate,
        ShippingRouteTrackingUpdate,
        ShippingRouteTrackingPublic,
        ShippingRouteTrackingsPublic,
        Any,
    ]
):
    """Router exposing tracking CRUD and advanced tracking endpoints."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the shipping route tracking router instance."""
        super().__init__(*args, **kwargs)
        # Ajouter les endpoints personnalisés après initialisation
        self.add_tracking_endpoints()

    def add_tracking_endpoints(self) -> None:
        """Register custom endpoints for tracking workflows."""

        @self.get(
            "/order/{order_id}",
            response_model=OrderTrackingResponse,
            summary="Get order tracking",
            description="Récupère le suivi complet d'une commande avec tous ses trackings",
        )
        async def get_order_tracking(
            order_id: uuid.UUID,
            session: SessionDep,
            _current_user: CurrentSuperUser,
        ):
            # Récupérer le tracking principal pour cette commande
            """Return tracking progress and consolidations for an order."""
            tracking = await self.crud.get_by_order_id(
                session=session, order_id=order_id
            )

            if not tracking:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No tracking found for this order",
                )

            # Récupérer tous les trackings par séquence
            trackings = await self.crud.get_trackings_by_order_sequence(
                session=session, order_id=order_id
            )

            # Récupérer les consolidations pour toutes les routes de cette commande
            consolidations = []
            for t in trackings:
                route_consolidations = await crud_shipping_route_tracking_consolidation.get_consolidations_for_route(
                    session=session,
                    route_id=t.route_id,
                )
                consolidations.extend(route_consolidations)

            status_definitions = await crud_status_definition.get_by_entity(
                session=session,
                entity="route_tracking",
            )
            status_by_id = {
                status_record.id: status_record for status_record in status_definitions
            }
            current_sequence, overall_status = _derive_order_overall_status(
                trackings,
                status_by_id=status_by_id,
            )
            exception_scenarios = _derive_order_exception_scenarios(
                trackings,
                status_by_id=status_by_id,
            )

            return OrderTrackingResponse(
                order_id=order_id,
                trackings=[
                    ShippingRouteTrackingPublic.model_validate(t) for t in trackings
                ],
                current_route_sequence=current_sequence,
                overall_status=overall_status,
                exception_scenarios=exception_scenarios,
                consolidations=[
                    ShippingRouteTrackingConsolidationPublic.model_validate(c)
                    for c in consolidations
                ],
            )

        @self.get(
            "/{tracking_id}/status",
            response_model=TrackingStatusResponse,
            summary="Get tracking status",
            description="Récupère le statut actuel d'un tracking",
        )
        async def get_tracking_status(
            tracking_id: uuid.UUID,
            session: SessionDep,
            _current_user: CurrentSuperUser,
        ):
            """Return the current status of a tracking record."""
            try:
                tracking = await self.crud.read(session=session, id=tracking_id)
            except RecordNotFoundError:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Tracking not found"
                )

            # Récupérer les détails du statut
            status_details = await self.crud.get_status_by_code(
                session=session,
                entity="shipping_route_tracking",
                status_code=tracking.status_id,
            )

            return TrackingStatusResponse(
                tracking_id=tracking_id,
                order_id=tracking.order_id,
                current_status=status_details.code,
                current_status_name=status_details.name,
                sequence_order=tracking.sequence_order,
                estimated_arrival=tracking.estimated_arrival,
                tracking_ref=tracking.tracking_ref,
            )

        @self.post(
            "/{tracking_id}/update-status",
            response_model=ShippingRouteTrackingPublic,
            summary="Update tracking status",
            description="Met à jour le statut d'un tracking avec validation des transitions",
        )
        async def update_tracking_status(
            tracking_id: uuid.UUID,
            request: UpdateStatusRequest,
            session: SessionDep,
            current_user: CurrentSuperUser,
        ):
            """Update tracking status with transition validation."""
            try:
                updated_tracking = await self.crud.update_status(
                    session=session,
                    tracking_id=tracking_id,
                    new_status_id=request.new_status_id,
                    changed_by=str(current_user.id),
                    reason=request.reason,
                )
                return ShippingRouteTrackingPublic.model_validate(updated_tracking)

            except RecordNotFoundError:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Tracking not found"
                )

            except ValueError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
                )

        @self.get(
            "/{tracking_id}/history",
            response_model=TrackingHistoryResponse,
            summary="Get tracking history",
            description="Récupère l'historique complet des changements de statut",
        )
        async def get_tracking_history(
            tracking_id: uuid.UUID,
            session: SessionDep,
            _current_user: CurrentSuperUser,
            limit: int = Query(
                default=100, le=500, description="Nombre maximum d'entrées"
            ),
        ):
            """Return tracking status-change history."""
            try:
                await self.crud.read(session=session, id=tracking_id)
            except RecordNotFoundError:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Tracking not found"
                )

            history = await self.crud.get_status_history(
                session=session, tracking_id=tracking_id, limit=limit
            )

            return TrackingHistoryResponse(
                tracking_id=tracking_id,
                history=[
                    ShippingRouteTrackingLogsPublic.model_validate(log)
                    for log in history
                ],
                total_changes=len(history),
            )

        @self.post(
            "/{tracking_id}/activate-next-route",
            response_model=ShippingRouteTrackingPublic | None,
            summary="Activate next route",
            description="Active la prochaine route dans la séquence pour progression multi-hop",
        )
        async def activate_next_route(
            tracking_id: uuid.UUID,
            session: SessionDep,
            current_user: CurrentSuperUser,
        ):
            """Activate the next route in a multi-hop tracking sequence."""
            try:
                next_tracking = await self.crud.activate_next_route(
                    session=session,
                    tracking_id=tracking_id,
                    user_id=current_user.id,
                )

                if next_tracking:
                    return ShippingRouteTrackingPublic.model_validate(next_tracking)
                else:
                    return None  # Pas de route suivante

            except ValueError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
                )


class Auth:
    """Authorization flags for tracking endpoints."""

    read = True
    create = True
    update = True
    delete = True
    read_superuser = True
    create_superuser = True
    update_superuser = True
    delete_superuser = True


# Router principal pour les trackings
shipping_route_tracking_router = ShippingRouteTrackingRouter(
    name="tracking",
    tags=["shipping"],
    crud=crud_shipping_route_tracking,
    schema_public=ShippingRouteTrackingPublic,
    schema_publics=ShippingRouteTrackingsPublic,
    schema_create=ShippingRouteTrackingCreate,
    schema_update=ShippingRouteTrackingUpdate,
    auth=Auth(),
    auto=True,
)


# Router simple pour les consolidations (BaseRouter standard)
class ConsolidationAuth:
    """Authorization flags for consolidation endpoints."""

    read = True
    create = True
    update = True
    delete = True
    read_superuser = True
    create_superuser = True
    update_superuser = True
    delete_superuser = True


# Router pour les consolidations
consolidation_router = BaseRouter(
    name="consolidation",
    tags=["shipping"],
    crud=crud_shipping_route_tracking_consolidation,
    schema_public=ShippingRouteTrackingConsolidationPublic,
    schema_publics=ShippingRouteTrackingConsolidationsPublic,
    schema_create=ShippingRouteTrackingConsolidationCreate,
    schema_update=ShippingRouteTrackingConsolidationUpdate,
    auth=ConsolidationAuth(),
    auto=True,
)


# Router simple pour les logs (lecture seule via APIRouter)
logs_router = APIRouter(
    prefix="/logs",
    tags=["shipping"],
)


@logs_router.get(
    "/tracking/{tracking_id}",
    response_model=list[ShippingRouteTrackingLogsPublic],
    summary="Get tracking logs",
    description="Récupère les logs pour un tracking spécifique",
)
async def get_tracking_logs(
    tracking_id: uuid.UUID,
    session: SessionDep,
    _current_user: CurrentSuperUser,
    limit: int = Query(default=100, le=500),
):
    """Return tracking log entries for a tracking record."""
    # On utilise directement le CRUD du tracking pour accéder aux logs
    history = await crud_shipping_route_tracking.get_status_history(
        session=session, tracking_id=tracking_id, limit=limit
    )

    return [ShippingRouteTrackingLogsPublic.model_validate(log) for log in history]
