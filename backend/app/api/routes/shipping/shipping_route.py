# mypy: disable-error-code="misc,no-untyped-def,type-arg"

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import Depends, HTTPException, Query
from sqlmodel import Field, SQLModel, col, select

from app.api.base_router import BaseRouter
from app.api.deps import CurrentUser, SessionDep, get_current_user_optional
from app.features.shipping.crud import crud_shipping_route
from app.features.shipping.models.route import (
    ShippingRoute,
    ShippingRouteCreate,
    ShippingRoutePublic,
    ShippingRoutesPublic,
    ShippingRouteUpdate,
)
from app.features.shipping.services import (
    ShippingCostSummary,
    calculate_shipping_for_routes,
)


# Modèles pour les coûts détaillés par tronçon (étape "devis shipping")
class ShippingSegmentCostResponse(SQLModel):
    """Coût détaillé d'un tronçon (une route) dans un chemin logistique."""

    route_id: uuid.UUID
    route_name: str | None = None
    fixed_fee: Decimal = Field(description="Forfait du tronçon")
    weight_fee: Decimal = Field(description="Part au poids facturable")
    value_fee: Decimal = Field(description="Part à la valeur marchandise")
    total_fee: Decimal = Field(description="Coût total du tronçon (bornes appliquées)")
    weight_unit: str = Field(description="Unité de poids facturée (kg/lb)")
    billable_weight: Decimal = Field(
        description="Poids facturable dans l'unité du tronçon"
    )
    eta_days: int | None = None
    carbon_footprint_kg_co2e: float | None = None
    pricing_effective: bool = Field(
        description="Le tarif du tronçon était-il dans sa fenêtre de date d'effet ?"
    )


class ShippingPathQuoteResponse(SQLModel):
    """Devis détaillé d'un chemin logistique complet (Route 1 + Route 2 + ...)."""

    label: str | None = None
    route_ids: list[uuid.UUID] = Field(description="Routes ordonnées du chemin")
    currency: str
    total_fee: Decimal = Field(description="Coût total du chemin")
    eta_days: int | None = None
    carbon_footprint_kg_co2e: float | None = None
    segments: list[ShippingSegmentCostResponse] = Field(default_factory=list)


class ShippingQuotePathRequest(SQLModel):
    label: str | None = Field(default=None, description="Libellé optionnel du chemin")
    route_ids: list[uuid.UUID] = Field(
        description="Routes ordonnées composant ce chemin (Route 1, Route 2, ...)"
    )


class ShippingQuoteRequest(SQLModel):
    paths: list[ShippingQuotePathRequest] = Field(
        description="Chemins candidats à chiffrer (un chemin par expédition)"
    )
    total_weight_kg: Decimal = Field(
        default=Decimal("0"), ge=0, description="Poids total facturable en kg"
    )
    declared_value: Decimal = Field(
        default=Decimal("0"), ge=0, description="Valeur marchandise déclarée"
    )
    currency: str = Field(default="EUR", min_length=1, max_length=8)
    as_of: datetime | None = Field(
        default=None,
        description="Date d'effet pour la sélection du tarif (défaut: maintenant)",
    )


class ShippingQuoteResponse(SQLModel):
    paths: list[ShippingPathQuoteResponse] = Field(default_factory=list)


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
    cost: ShippingPathQuoteResponse | None = Field(
        default=None,
        description=(
            "Coût détaillé du chemin si les paramètres de chiffrage "
            "(total_weight_kg / declared_value / currency) sont fournis"
        ),
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


def _segment_cost_response(
    summary: ShippingCostSummary,
) -> list[ShippingSegmentCostResponse]:
    return [
        ShippingSegmentCostResponse(
            route_id=segment.route_id,
            route_name=segment.route_name,
            fixed_fee=segment.fixed_fee,
            weight_fee=segment.weight_fee,
            value_fee=segment.value_fee,
            total_fee=segment.total_fee,
            weight_unit=segment.weight_unit,
            billable_weight=segment.billable_weight,
            eta_days=segment.eta_days,
            carbon_footprint_kg_co2e=segment.carbon_footprint_kg_co2e,
            pricing_effective=segment.pricing_effective,
        )
        for segment in summary.breakdown
    ]


def _path_quote_response(
    *,
    summary: ShippingCostSummary,
    route_ids: list[uuid.UUID],
    label: str | None = None,
) -> ShippingPathQuoteResponse:
    return ShippingPathQuoteResponse(
        label=label,
        route_ids=route_ids,
        currency=summary.currency,
        total_fee=summary.total_fee,
        eta_days=summary.eta_days,
        carbon_footprint_kg_co2e=summary.carbon_footprint_kg_co2e,
        segments=_segment_cost_response(summary),
    )


async def _load_active_routes(
    session: SessionDep,
    route_ids: list[uuid.UUID],
) -> dict[uuid.UUID, ShippingRoute]:
    distinct_ids = list(dict.fromkeys(route_ids))
    if not distinct_ids:
        return {}

    statement = select(ShippingRoute).where(
        col(ShippingRoute.id).in_(distinct_ids),
        col(ShippingRoute.is_active).is_(True),
    )
    result = await session.exec(statement)
    route_by_id = {route.id: route for route in result.all()}

    missing = [str(rid) for rid in distinct_ids if rid not in route_by_id]
    if missing:
        raise HTTPException(
            status_code=400,
            detail="Unknown or inactive shipping routes: " + ", ".join(missing),
        )
    return route_by_id


class ShippingRouteRouter(
    BaseRouter[
        ShippingRoute,
        ShippingRouteCreate,
        ShippingRouteUpdate,
        ShippingRoutePublic,
        ShippingRoutesPublic,
        Any,
    ]
):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        # Ajouter les endpoints personnalisés après initialisation
        self.add_routing_endpoints()

    def add_routing_endpoints(self) -> None:
        """Ajoute les endpoints personnalisés de routage"""

        @self.post(
            "/quote",
            response_model=ShippingQuoteResponse,
            summary="Quote shipping paths",
            description=(
                "Étape 'devis shipping' : recalcule côté serveur le coût détaillé "
                "tronçon par tronçon de chaque chemin candidat."
            ),
        )
        async def quote_shipping_paths(
            payload: ShippingQuoteRequest,
            session: SessionDep,
            _current_user: CurrentUser | None = Depends(get_current_user_optional),
        ):
            if not payload.paths:
                raise HTTPException(
                    status_code=400, detail="At least one path is required"
                )

            all_route_ids = [
                route_id for path in payload.paths for route_id in path.route_ids
            ]
            route_by_id = await _load_active_routes(session, all_route_ids)

            quoted_paths: list[ShippingPathQuoteResponse] = []
            for path in payload.paths:
                if not path.route_ids:
                    raise HTTPException(
                        status_code=400, detail="A path must contain at least one route"
                    )
                ordered_routes = [route_by_id[rid] for rid in path.route_ids]
                summary = calculate_shipping_for_routes(
                    routes=ordered_routes,
                    total_weight_kg=payload.total_weight_kg,
                    declared_value=payload.declared_value,
                    currency=payload.currency,
                    as_of=payload.as_of,
                )
                quoted_paths.append(
                    _path_quote_response(
                        summary=summary,
                        route_ids=path.route_ids,
                        label=path.label,
                    )
                )

            return ShippingQuoteResponse(paths=quoted_paths)

        @self.get(
            "/paths/{from_place_id}/{to_place_id}",
            response_model=RoutePathsResponse,
            summary="Get all paths between places",
            description=(
                "Récupère tous les chemins possibles entre deux lieux. "
                "Si total_weight_kg / declared_value / currency sont fournis, "
                "chaque chemin est aussi chiffré (coûts détaillés par tronçon)."
            ),
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
            total_weight_kg: Decimal | None = Query(
                None, ge=0, description="Poids total facturable (active le chiffrage)"
            ),
            declared_value: Decimal | None = Query(
                None, ge=0, description="Valeur marchandise déclarée"
            ),
            currency: str | None = Query(
                None, description="Devise du chiffrage (ex: EUR, XPF)"
            ),
            as_of: datetime | None = Query(
                None, description="Date d'effet pour la sélection du tarif"
            ),
            _current_user: CurrentUser | None = Depends(get_current_user_optional),
        ):
            paths = await self.crud.get_routes_between_places(
                session=session,
                from_place_id=from_place_id,
                to_place_id=to_place_id,
                is_to_customer=is_to_customer,
                max_hops=max_hops,
            )

            should_quote = currency is not None and (
                total_weight_kg is not None or declared_value is not None
            )

            response_paths = []
            for path in paths:
                operators = [route.operator for route in path if route.operator]
                total_priority = sum(route.priority or 999 for route in path)

                cost: ShippingPathQuoteResponse | None = None
                if should_quote:
                    summary = calculate_shipping_for_routes(
                        routes=list(path),
                        total_weight_kg=total_weight_kg or Decimal("0"),
                        declared_value=declared_value or Decimal("0"),
                        currency=currency or "EUR",
                        as_of=as_of,
                    )
                    cost = _path_quote_response(
                        summary=summary,
                        route_ids=[route.id for route in path],
                    )

                response_paths.append(
                    RoutePathResponse(
                        hops=len(path),
                        routes=[
                            ShippingRoutePublic.model_validate(route) for route in path
                        ],
                        total_priority=total_priority,
                        operators=operators,
                        cost=cost,
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
            _current_user: CurrentUser | None = Depends(get_current_user_optional),
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
            _current_user: CurrentUser | None = Depends(get_current_user_optional),
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
