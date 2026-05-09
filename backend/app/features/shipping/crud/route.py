"""
CRUD for delivery routes and their steps.
"""

# mypy: disable-error-code="arg-type,attr-defined"

import uuid
from typing import Any

from sqlmodel import and_, col, or_, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.shipping.models.route import (
    ShippingRoute,
    ShippingRouteCreate,
    ShippingRouteUpdate,
)


class ShippingRouteCrud(
    CrudBase[ShippingRoute, ShippingRouteCreate, ShippingRouteUpdate]
):
    async def get_routes_between_places(
        self,
        session: AsyncSession,
        from_place_id: uuid.UUID,
        to_place_id: uuid.UUID,
        is_to_customer: bool | None = None,
        max_hops: int = 10,
    ) -> list[list[ShippingRoute]]:
        """
        Retrieve all possible paths between two places.
        Uses a search algorithm going back from the destination.

        Returns:
            list[list[ShippingRoute]]: List of paths, each path being a list of ordered routes
        """

        # Cache to avoid repeated queries
        all_routes_cache = {}

        async def get_routes_to_place(place_id: uuid.UUID) -> list[ShippingRoute]:
            """Cache of routes leading to a given place"""
            if place_id not in all_routes_cache:
                conditions = [
                    ShippingRoute.to_place_id == place_id,
                    col(ShippingRoute.is_active).is_(True),
                ]

                if is_to_customer is not None:
                    conditions.append(ShippingRoute.is_to_customer == is_to_customer)

                statement = (
                    select(ShippingRoute)
                    .where(and_(*conditions))
                    .order_by(col(ShippingRoute.priority).asc())
                )

                result = await session.exec(statement)
                all_routes_cache[place_id] = list(result.all())

            return all_routes_cache[place_id]

        async def find_paths_recursive(
            current_destination: uuid.UUID,
            target_origin: uuid.UUID,
            current_path: list[ShippingRoute],
            visited_places: set[uuid.UUID],
            depth: int = 0,
        ) -> list[list[ShippingRoute]]:
            """
            Recherche récursive des chemins en remontant depuis la destination
            """
            # Limite de profondeur pour éviter les boucles infinies
            if depth >= max_hops:
                return []

            # Si on a atteint l'origine, on a trouvé un chemin complet
            if current_destination == target_origin:
                return [list(reversed(current_path))]  # Inverser car on remonte

            # Éviter les cycles
            if current_destination in visited_places:
                return []

            all_paths = []
            visited_places.add(current_destination)

            # Récupérer toutes les routes qui arrivent à la destination actuelle
            incoming_routes = await get_routes_to_place(current_destination)

            for route in incoming_routes:
                # Ajouter cette route au chemin actuel
                new_path = current_path + [route]
                new_visited = visited_places.copy()

                # Continuer la recherche depuis l'origine de cette route
                sub_paths = await find_paths_recursive(
                    current_destination=route.from_place_id,
                    target_origin=target_origin,
                    current_path=new_path,
                    visited_places=new_visited,
                    depth=depth + 1,
                )

                all_paths.extend(sub_paths)

            return all_paths

        # Commencer la recherche depuis la destination finale
        paths = await find_paths_recursive(
            current_destination=to_place_id,
            target_origin=from_place_id,
            current_path=[],
            visited_places=set(),
            depth=0,
        )

        # Trier les chemins par priorité (somme des priorités des routes)
        def calculate_path_priority(path: list[ShippingRoute]) -> tuple[int, float]:
            """Calcule la priorité d'un chemin (nombre d'étapes, puis somme des priorités)"""
            total_priority = sum(route.priority or 999 for route in path)
            return (len(path), total_priority)

        paths.sort(key=calculate_path_priority)

        return paths

    async def get_optimal_route_between_places(
        self,
        session: AsyncSession,
        from_place_id: uuid.UUID,
        to_place_id: uuid.UUID,
        is_to_customer: bool | None = None,
        prefer_direct: bool = True,
    ) -> list[ShippingRoute] | None:
        """
        Récupère le chemin optimal entre deux lieux.

        Args:
            prefer_direct: Si True, privilégie les routes directes, sinon le chemin le plus court

        Returns:
            list[ShippingRoute] | None: Le chemin optimal ou None si aucun chemin trouvé
        """
        paths = await self.get_routes_between_places(
            session, from_place_id, to_place_id, is_to_customer
        )

        if not paths:
            return None

        if prefer_direct:
            # Privilégier les routes directes (1 étape)
            direct_paths = [path for path in paths if len(path) == 1]
            if direct_paths:
                return direct_paths[0]

        # Sinon retourner le premier chemin (déjà trié par priorité)
        return paths[0]

    async def get_routing_statistics(
        self,
        session: AsyncSession,
        from_place_id: uuid.UUID,
        to_place_id: uuid.UUID,
        is_to_customer: bool | None = None,
    ) -> dict[str, Any]:
        """
        Récupère des statistiques sur les chemins disponibles entre deux lieux.

        Returns:
            dict: Statistiques incluant nombre de chemins, longueurs min/max, etc.
        """
        paths = await self.get_routes_between_places(
            session, from_place_id, to_place_id, is_to_customer
        )

        if not paths:
            return {
                "total_paths": 0,
                "direct_paths": 0,
                "min_hops": 0,
                "max_hops": 0,
                "avg_hops": 0,
                "has_direct_route": False,
            }

        path_lengths = [len(path) for path in paths]
        direct_paths = len([p for p in paths if len(p) == 1])

        return {
            "total_paths": len(paths),
            "direct_paths": direct_paths,
            "min_hops": min(path_lengths),
            "max_hops": max(path_lengths),
            "avg_hops": sum(path_lengths) / len(path_lengths),
            "has_direct_route": direct_paths > 0,
            "path_details": [
                {
                    "hops": len(path),
                    "route_names": [
                        route.name or f"Route-{route.id}" for route in path
                    ],
                    "operators": [route.operator for route in path if route.operator],
                }
                for path in paths[:5]  # Limiter à 5 premiers chemins pour les détails
            ],
        }

    async def get_routes_from_place(
        self,
        session: AsyncSession,
        from_place_id: uuid.UUID,
        mode: str | None = None,
    ) -> list[ShippingRoute]:
        """Récupère toutes les routes depuis un lieu"""

        conditions = [
            ShippingRoute.from_place_id == from_place_id,
            col(ShippingRoute.is_active).is_(True),
        ]

        if mode:
            conditions.append(ShippingRoute.mode == mode)

        statement = (
            select(ShippingRoute)
            .where(and_(*conditions))
            .order_by(col(ShippingRoute.priority).asc())
        )

        result = await session.exec(statement)
        return list(result.all())

    async def get_routes_to_place(
        self,
        session: AsyncSession,
        to_place_id: uuid.UUID,
        mode: str | None = None,
    ) -> list[ShippingRoute]:
        """Récupère toutes les routes vers un lieu"""

        conditions = [
            ShippingRoute.to_place_id == to_place_id,
            col(ShippingRoute.is_active).is_(True),
        ]

        if mode:
            conditions.append(ShippingRoute.mode == mode)

        statement = (
            select(ShippingRoute)
            .where(and_(*conditions))
            .order_by(col(ShippingRoute.priority).asc())
        )

        result = await session.exec(statement)
        return list(result.all())

    async def get_intermediary_routes(
        self,
        session: AsyncSession,
        allow_consolidation: bool | None = None,
    ) -> list[ShippingRoute]:
        """Récupère les routes intermédiaires (non client final)"""

        conditions = [
            col(ShippingRoute.is_to_customer).is_(False),
            col(ShippingRoute.is_active).is_(True),
        ]

        if allow_consolidation is not None:
            conditions.append(ShippingRoute.allow_consolidation == allow_consolidation)

        statement = (
            select(ShippingRoute)
            .where(and_(*conditions))
            .order_by(col(ShippingRoute.priority).asc())
        )

        result = await session.exec(statement)
        return list(result.all())

    async def get_customer_routes(
        self,
        session: AsyncSession,
        from_place_id: uuid.UUID | None = None,
    ) -> list[ShippingRoute]:
        """Récupère les routes vers les clients"""

        conditions = [
            col(ShippingRoute.is_to_customer).is_(True),
            col(ShippingRoute.is_active).is_(True),
        ]

        if from_place_id:
            conditions.append(ShippingRoute.from_place_id == from_place_id)

        statement = (
            select(ShippingRoute)
            .where(and_(*conditions))
            .order_by(col(ShippingRoute.priority).asc())
        )

        result = await session.exec(statement)
        return list(result.all())

    async def search_routes(
        self,
        session: AsyncSession,
        search_term: str,
        mode: str | None = None,
        is_to_customer: bool | None = None,
    ) -> list[ShippingRoute]:
        """Recherche de routes par nom, opérateur ou notes"""

        from app.features.place.models import Place

        conditions = [col(ShippingRoute.is_active).is_(True)]

        if mode:
            conditions.append(ShippingRoute.mode == mode)

        if is_to_customer is not None:
            conditions.append(ShippingRoute.is_to_customer == is_to_customer)

        # Recherche dans différents champs
        search_conditions = [
            col(ShippingRoute.name).ilike(f"%{search_term}%"),
            col(ShippingRoute.operator).ilike(f"%{search_term}%"),
            col(ShippingRoute.operator_ref).ilike(f"%{search_term}%"),
            col(ShippingRoute.notes).ilike(f"%{search_term}%"),
        ]

        statement = (
            select(ShippingRoute)
            .join(Place, ShippingRoute.from_place_id == Place.id, isouter=True)
            .where(
                and_(
                    *conditions,
                    or_(
                        *search_conditions,
                        col(Place.name).ilike(f"%{search_term}%"),
                    ),
                )
            )
            .order_by(col(ShippingRoute.priority).asc())
        )

        result = await session.exec(statement)
        return list(result.all())

    async def get_routes_by_partner(
        self,
        session: AsyncSession,
        partner_id: uuid.UUID,
        is_origin: bool = True,
    ) -> list[ShippingRoute]:
        """Récupère les routes d'un partenaire"""

        if is_origin:
            condition = ShippingRoute.from_partner_id == partner_id
        else:
            condition = ShippingRoute.to_partner_id == partner_id

        statement = (
            select(ShippingRoute)
            .where(
                and_(
                    condition,
                    col(ShippingRoute.is_active).is_(True),
                )
            )
            .order_by(col(ShippingRoute.priority).asc())
        )

        result = await session.exec(statement)
        return list(result.all())


crud_shipping_route = ShippingRouteCrud(
    model=ShippingRoute,
    schema_create=ShippingRouteCreate,
    schema_update=ShippingRouteUpdate,
    default_filter=and_(
        col(ShippingRoute.is_active).is_(True),
    ),
    order_by=col(ShippingRoute.priority).asc(),
)
