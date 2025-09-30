import uuid
from typing import Any

from fastapi import Depends, HTTPException, Query, status
from sqlmodel import Field, SQLModel

from app.api.base_router import BaseRouter
from app.api.deps import CurrentUser, SessionDep, get_current_user_optional
from app.features.shipping.crud import (
    crud_shipping_route_tracking,
    crud_shipping_route_tracking_consolidation,
)
from app.features.shipping.models.shipping_route_tracking import (
    ShippingRouteTracking,
    ShippingRouteTrackingCreate,
    ShippingRouteTrackingPublic,
    ShippingRouteTrackingsPublic,
    ShippingRouteTrackingUpdate,
    ShippingRouteTrackingConsolidation,
    ShippingRouteTrackingConsolidationCreate,
    ShippingRouteTrackingConsolidationPublic,
    ShippingRouteTrackingConsolidationsPublic,
    ShippingRouteTrackingConsolidationUpdate,
    ShippingRouteTrackingLogs,
    ShippingRouteTrackingLogsPublic,
)


# Modèles de requête pour les endpoints POST
class UpdateStatusRequest(SQLModel):
    """Requête pour mettre à jour le statut d'un tracking"""
    
    new_status_id: uuid.UUID = Field(description="Nouveau statut")
    reason: str | None = Field(default=None, description="Raison du changement")


# Modèles de réponse pour les endpoints spécialisés
class TrackingStatusResponse(SQLModel):
    """Réponse pour le statut d'un tracking"""
    
    tracking_id: uuid.UUID = Field(description="ID du tracking")
    order_id: uuid.UUID = Field(description="ID de la commande")
    current_status: str = Field(description="Statut actuel")
    current_status_name: str = Field(description="Nom du statut actuel")
    sequence_order: int = Field(description="Ordre dans la séquence")
    estimated_arrival: str | None = Field(default=None, description="Arrivée estimée")
    tracking_ref: str | None = Field(default=None, description="Référence de suivi")


class TrackingHistoryResponse(SQLModel):
    """Réponse pour l'historique d'un tracking"""
    
    tracking_id: uuid.UUID = Field(description="ID du tracking")
    history: list[ShippingRouteTrackingLogsPublic] = Field(
        description="Historique des changements de statut"
    )
    total_changes: int = Field(description="Nombre total de changements")


class OrderTrackingResponse(SQLModel):
    """Réponse complète pour le suivi d'une commande"""
    
    order_id: uuid.UUID = Field(description="ID de la commande")
    trackings: list[ShippingRouteTrackingPublic] = Field(
        description="Liste des trackings pour cette commande"
    )
    current_route_sequence: int | None = Field(
        default=None, description="Séquence de route actuelle"
    )
    overall_status: str = Field(description="Statut global de la commande")
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
        type(crud_shipping_route_tracking),
    ]
):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Ajouter les endpoints personnalisés après initialisation
        self.add_tracking_endpoints()

    def add_tracking_endpoints(self):
        """Ajoute les endpoints personnalisés pour le tracking"""

        @self.get(
            "/order/{order_id}",
            response_model=OrderTrackingResponse,
            summary="Get order tracking",
            description="Récupère le suivi complet d'une commande avec tous ses trackings",
        )
        async def get_order_tracking(
            order_id: uuid.UUID,
            session: SessionDep,
            current_user: CurrentUser | None = Depends(get_current_user_optional),
        ):
            # Récupérer le tracking principal pour cette commande
            tracking = await self.crud.get_by_order_id(
                session=session, order_id=order_id
            )
            
            if not tracking:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No tracking found for this order"
                )

            # Récupérer tous les trackings par séquence
            trackings = await self.crud.get_trackings_by_order_sequence(
                session=session, order_id=order_id
            )

            # Récupérer les consolidations pour toutes les routes de cette commande
            consolidations = []
            for t in trackings:
                route_consolidations = await self.crud.get_consolidations_for_route(
                    session=session, route_id=t.route_id
                )
                consolidations.extend(route_consolidations)

            # Déterminer la séquence actuelle
            current_sequence = max((t.sequence_order for t in trackings), default=0)
            
            # Déterminer le statut global (basé sur le tracking avec la séquence la plus élevée)
            current_tracking = max(trackings, key=lambda x: x.sequence_order)
            status_details = await self.crud.get_status_by_code(
                session=session, entity="shipping_route_tracking", status_code=current_tracking.status_id
            )
            overall_status = status_details.code if status_details else "unknown"

            return OrderTrackingResponse(
                order_id=order_id,
                trackings=[ShippingRouteTrackingPublic.model_validate(t) for t in trackings],
                current_route_sequence=current_sequence,
                overall_status=overall_status,
                consolidations=[ShippingRouteTrackingConsolidationPublic.model_validate(c) for c in consolidations],
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
            current_user: CurrentUser | None = Depends(get_current_user_optional),
        ):
            tracking = await self.crud.get(session=session, id=tracking_id)
            
            if not tracking:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Tracking not found"
                )

            # Récupérer les détails du statut
            status_details = await self.crud.get_status_by_code(
                session=session, entity="shipping_route_tracking", status_code=tracking.status_id
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
            current_user: CurrentUser,
        ):
            try:
                updated_tracking = await self.crud.update_status(
                    session=session,
                    tracking_id=tracking_id,
                    new_status_id=request.new_status_id,
                    user_id=current_user.id,
                    reason=request.reason,
                )
                return ShippingRouteTrackingPublic.model_validate(updated_tracking)
                
            except ValueError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(e)
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
            limit: int = Query(default=100, le=500, description="Nombre maximum d'entrées"),
            current_user: CurrentUser | None = Depends(get_current_user_optional),
        ):
            tracking = await self.crud.get(session=session, id=tracking_id)
            
            if not tracking:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Tracking not found"
                )

            history = await self.crud.get_status_history(
                session=session, tracking_id=tracking_id, limit=limit
            )

            return TrackingHistoryResponse(
                tracking_id=tracking_id,
                history=[ShippingRouteTrackingLogsPublic.model_validate(log) for log in history],
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
            current_user: CurrentUser,
        ):
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
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(e)
                )


class Auth:
    read = True
    create = True  
    update = True
    delete = True


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
    read = True
    create = True
    update = True
    delete = True


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
from fastapi import APIRouter

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
    limit: int = Query(default=100, le=500),
    current_user: CurrentUser | None = Depends(get_current_user_optional),
):
    """Récupère l'historique des logs pour un tracking"""
    # On utilise directement le CRUD du tracking pour accéder aux logs
    history = await crud_shipping_route_tracking.get_status_history(
        session=session, tracking_id=tracking_id, limit=limit
    )
    
    return [ShippingRouteTrackingLogsPublic.model_validate(log) for log in history]