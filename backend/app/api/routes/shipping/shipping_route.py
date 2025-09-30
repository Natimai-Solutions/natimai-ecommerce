import uuid

from fastapi import Depends, HTTPException, Query
from sqlmodel import Field, SQLModel

from app.api.base_router import BaseRouter
from app.api.deps import CurrentUser, SessionDep, get_current_user_optional
from app.features.shipping.crud import crud_shipping_route
from app.features.shipping.models.shipping_route import (
    ShippingRoute,
    ShippingRouteCreate,
    ShippingRoutePublic,
    ShippingRoutesPublic,
    ShippingRouteUpdate,
)


# Modèles pour les réponses des endpoints de routage
class RoutePathResponse(SQLModel):
    """Représente un chemin complet entre deux lieux"""

    hops: int = Field(description="Nombre d'étapes dans le chemin")
    routes: list[ShippingRoutePublic] = Field(
        description="Liste des routes composant le chemin"
    )
    total_priority: float = Field(description="Priorité totale du chemin")
    operators: list[str] = Field(
        default_factory=list, description="Liste des opérateurs impliqués"
    )


class RoutePathsResponse(SQLModel):
    """Réponse contenant tous les chemins disponibles"""

    paths: list[RoutePathResponse] = Field(
        description="Liste de tous les chemins disponibles"
    )
    total_count: int = Field(description="Nombre total de chemins trouvés")


class RoutingStatisticsResponse(SQLModel):
    """Statistiques sur les chemins de routage"""

    total_paths: int = Field(description="Nombre total de chemins")
    direct_paths: int = Field(description="Nombre de chemins directs")
    min_hops: int = Field(description="Nombre minimum d'étapes")
    max_hops: int = Field(description="Nombre maximum d'étapes")
    avg_hops: float = Field(description="Nombre moyen d'étapes")
    has_direct_route: bool = Field(description="Existence d'une route directe")
    path_details: list[dict] = Field(
        default_factory=list, description="Détails des premiers chemins"
    )


class ShippingRouteRouter(
    BaseRouter[
        ShippingRoute,
        ShippingRouteCreate,
        ShippingRouteUpdate,
        ShippingRoutePublic,
        ShippingRoutesPublic,
        type(crud_shipping_route),
    ]
):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Ajouter les endpoints personnalisés après initialisation
        self.add_routing_endpoints()

    def add_routing_endpoints(self):
        """Ajoute les endpoints personnalisés de routage"""

        @self.get(
            "/paths/{from_place_id}/{to_place_id}",
            response_model=RoutePathsResponse,
            summary="Get all paths between places",
            description="Récupère tous les chemins possibles entre deux lieux",
        )
        async def get_all_paths(
            from_place_id: uuid.UUID,
            to_place_id: uuid.UUID,
            session: SessionDep,
            is_to_customer: bool | None = Query(
                None, description="Filtrer par type de destination"
            ),
            max_hops: int = Query(
                10, ge=1, le=20, description="Nombre maximum d'étapes"
            ),
            current_user: CurrentUser | None = Depends(get_current_user_optional),
        ):
            paths = await self.crud.get_routes_between_places(
                session=session,
                from_place_id=from_place_id,
                to_place_id=to_place_id,
                is_to_customer=is_to_customer,
                max_hops=max_hops,
            )

            response_paths = []
            for path in paths:
                operators = [route.operator for route in path if route.operator]
                total_priority = sum(route.priority or 999 for route in path)

                response_paths.append(
                    RoutePathResponse(
                        hops=len(path),
                        routes=[
                            ShippingRoutePublic.model_validate(route) for route in path
                        ],
                        total_priority=total_priority,
                        operators=operators,
                    )
                )

            return RoutePathsResponse(
                paths=response_paths, total_count=len(response_paths)
            )

        @self.get(
            "/optimal/{from_place_id}/{to_place_id}",
            response_model=RoutePathResponse | None,
            summary="Get optimal path between places",
            description="Récupère le chemin optimal entre deux lieux",
        )
        async def get_optimal_path(
            from_place_id: uuid.UUID,
            to_place_id: uuid.UUID,
            session: SessionDep,
            is_to_customer: bool | None = Query(
                None, description="Filtrer par type de destination"
            ),
            prefer_direct: bool = Query(
                True, description="Privilégier les routes directes"
            ),
            current_user: CurrentUser | None = Depends(get_current_user_optional),
        ):
            path = await self.crud.get_optimal_route_between_places(
                session=session,
                from_place_id=from_place_id,
                to_place_id=to_place_id,
                is_to_customer=is_to_customer,
                prefer_direct=prefer_direct,
            )

            if not path:
                raise HTTPException(
                    status_code=404, detail="No route found between these places"
                )

            operators = [route.operator for route in path if route.operator]
            total_priority = sum(route.priority or 999 for route in path)

            return RoutePathResponse(
                hops=len(path),
                routes=[ShippingRoutePublic.model_validate(route) for route in path],
                total_priority=total_priority,
                operators=operators,
            )

        @self.get(
            "/statistics/{from_place_id}/{to_place_id}",
            response_model=RoutingStatisticsResponse,
            summary="Get routing statistics",
            description="Récupère des statistiques sur les chemins disponibles entre deux lieux",
        )
        async def get_routing_statistics(
            from_place_id: uuid.UUID,
            to_place_id: uuid.UUID,
            session: SessionDep,
            is_to_customer: bool | None = Query(
                None, description="Filtrer par type de destination"
            ),
            current_user: CurrentUser | None = Depends(get_current_user_optional),
        ):
            stats = await self.crud.get_routing_statistics(
                session=session,
                from_place_id=from_place_id,
                to_place_id=to_place_id,
                is_to_customer=is_to_customer,
            )

            return RoutingStatisticsResponse(**stats)


class Auth:
    read = True
    create = True
    update = True
    delete = True


# Router pour les routes de livraison
shipping_route_router = ShippingRouteRouter(
    name="route",
    tags=["shipping"],
    crud=crud_shipping_route,
    schema_public=ShippingRoutePublic,
    schema_publics=ShippingRoutesPublic,
    schema_create=ShippingRouteCreate,
    schema_update=ShippingRouteUpdate,
    auth=Auth(),
    auto=True,
)
