"""
CRUD pour les routes de livraison et leurs étapes.
"""

import uuid
from typing import Optional

from sqlmodel import and_, select, or_
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.shipping.models.shipping_route import (
    ShippingRoute,
    ShippingRouteCreate,
    ShippingRouteUpdate,
    ShippingRouteStep,
    ShippingRouteStepCreate,
    ShippingRouteStepUpdate,
)


class ShippingRouteCrud(CrudBase[ShippingRoute, ShippingRouteCreate, ShippingRouteUpdate]):
    
    async def get_routes_between_places(
        self,
        session: AsyncSession,
        from_place_id: uuid.UUID,
        to_place_id: uuid.UUID,
        is_to_customer: Optional[bool] = None,
        max_hops: int = 10,
    ) -> list[list[ShippingRoute]]:
        """
        Récupère tous les chemins possibles entre deux lieux.
        Utilise un algorithme de recherche en remontant depuis la destination.
        
        Returns:
            list[list[ShippingRoute]]: Liste des chemins, chaque chemin étant une liste de routes ordonnées
        """
        
        # Cache pour éviter les requêtes répétées
        all_routes_cache = {}
        
        async def get_routes_to_place(place_id: uuid.UUID) -> list[ShippingRoute]:
            """Cache des routes menant à un lieu donné"""
            if place_id not in all_routes_cache:
                conditions = [
                    ShippingRoute.to_place_id == place_id,
                    ShippingRoute.is_active.is_(True),
                ]
                
                if is_to_customer is not None:
                    conditions.append(ShippingRoute.is_to_customer == is_to_customer)
                
                statement = (
                    select(ShippingRoute)
                    .where(and_(*conditions))
                    .order_by(ShippingRoute.priority.asc())
                )
                
                result = await session.exec(statement)
                all_routes_cache[place_id] = result.all()
            
            return all_routes_cache[place_id]
        
        async def find_paths_recursive(
            current_destination: uuid.UUID,
            target_origin: uuid.UUID,
            current_path: list[ShippingRoute],
            visited_places: set[uuid.UUID],
            depth: int = 0
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
                    depth=depth + 1
                )
                
                all_paths.extend(sub_paths)
            
            return all_paths
        
        # Commencer la recherche depuis la destination finale
        paths = await find_paths_recursive(
            current_destination=to_place_id,
            target_origin=from_place_id,
            current_path=[],
            visited_places=set(),
            depth=0
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
        is_to_customer: Optional[bool] = None,
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
        is_to_customer: Optional[bool] = None,
    ) -> dict:
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
                    "route_names": [route.name or f"Route-{route.id}" for route in path],
                    "operators": [route.operator for route in path if route.operator],
                }
                for path in paths[:5]  # Limiter à 5 premiers chemins pour les détails
            ]
        }
    
    async def get_routes_from_place(
        self,
        session: AsyncSession,
        from_place_id: uuid.UUID,
        mode: Optional[str] = None,
    ) -> list[ShippingRoute]:
        """Récupère toutes les routes depuis un lieu"""
        
        conditions = [
            ShippingRoute.from_place_id == from_place_id,
            ShippingRoute.is_active.is_(True),
        ]
        
        if mode:
            conditions.append(ShippingRoute.mode == mode)
        
        statement = (
            select(ShippingRoute)
            .where(and_(*conditions))
            .order_by(ShippingRoute.priority.asc())
        )
        
        result = await session.exec(statement)
        return result.all()
    
    async def get_routes_to_place(
        self,
        session: AsyncSession,
        to_place_id: uuid.UUID,
        mode: Optional[str] = None,
    ) -> list[ShippingRoute]:
        """Récupère toutes les routes vers un lieu"""
        
        conditions = [
            ShippingRoute.to_place_id == to_place_id,
            ShippingRoute.is_active.is_(True),
        ]
        
        if mode:
            conditions.append(ShippingRoute.mode == mode)
        
        statement = (
            select(ShippingRoute)
            .where(and_(*conditions))
            .order_by(ShippingRoute.priority.asc())
        )
        
        result = await session.exec(statement)
        return result.all()
    
    async def get_intermediary_routes(
        self,
        session: AsyncSession,
        allow_consolidation: Optional[bool] = None,
    ) -> list[ShippingRoute]:
        """Récupère les routes intermédiaires (non client final)"""
        
        conditions = [
            ShippingRoute.is_to_customer.is_(False),
            ShippingRoute.is_active.is_(True),
        ]
        
        if allow_consolidation is not None:
            conditions.append(ShippingRoute.allow_consolidation == allow_consolidation)
        
        statement = (
            select(ShippingRoute)
            .where(and_(*conditions))
            .order_by(ShippingRoute.priority.asc())
        )
        
        result = await session.exec(statement)
        return result.all()
    
    async def get_customer_routes(
        self,
        session: AsyncSession,
        from_place_id: Optional[uuid.UUID] = None,
    ) -> list[ShippingRoute]:
        """Récupère les routes vers les clients"""
        
        conditions = [
            ShippingRoute.is_to_customer.is_(True),
            ShippingRoute.is_active.is_(True),
        ]
        
        if from_place_id:
            conditions.append(ShippingRoute.from_place_id == from_place_id)
        
        statement = (
            select(ShippingRoute)
            .where(and_(*conditions))
            .order_by(ShippingRoute.priority.asc())
        )
        
        result = await session.exec(statement)
        return result.all()
    
    async def search_routes(
        self,
        session: AsyncSession,
        search_term: str,
        mode: Optional[str] = None,
        is_to_customer: Optional[bool] = None,
    ) -> list[ShippingRoute]:
        """Recherche de routes par nom, opérateur ou notes"""
        
        from app.features.shipping.models.place import Place
        
        conditions = [ShippingRoute.is_active.is_(True)]
        
        if mode:
            conditions.append(ShippingRoute.mode == mode)
        
        if is_to_customer is not None:
            conditions.append(ShippingRoute.is_to_customer == is_to_customer)
        
        # Recherche dans différents champs
        search_conditions = [
            ShippingRoute.name.ilike(f"%{search_term}%"),
            ShippingRoute.operator.ilike(f"%{search_term}%"),
            ShippingRoute.operator_ref.ilike(f"%{search_term}%"),
            ShippingRoute.notes.ilike(f"%{search_term}%"),
        ]
        
        statement = (
            select(ShippingRoute)
            .join(Place, ShippingRoute.from_place_id == Place.id, isouter=True)
            .where(
                and_(
                    *conditions,
                    or_(
                        *search_conditions,
                        Place.name.ilike(f"%{search_term}%"),
                    )
                )
            )
            .order_by(ShippingRoute.priority.asc())
        )
        
        result = await session.exec(statement)
        return result.all()
    
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
                    ShippingRoute.is_active.is_(True),
                )
            )
            .order_by(ShippingRoute.priority.asc())
        )
        
        result = await session.exec(statement)
        return result.all()


class ShippingRouteStepCrud(CrudBase[ShippingRouteStep, ShippingRouteStepCreate, ShippingRouteStepUpdate]):
    
    async def get_steps_for_route(
        self,
        session: AsyncSession,
        route_id: uuid.UUID,
    ) -> list[ShippingRouteStep]:
        """Récupère toutes les étapes d'une route"""
        
        statement = (
            select(ShippingRouteStep)
            .where(
                and_(
                    ShippingRouteStep.route_id == route_id,
                    ShippingRouteStep.is_active.is_(True),
                )
            )
            .order_by(ShippingRouteStep.sequence.asc())
        )
        
        result = await session.exec(statement)
        return result.all()
    
    async def get_step_by_sequence(
        self,
        session: AsyncSession,
        route_id: uuid.UUID,
        sequence: int,
    ) -> ShippingRouteStep | None:
        """Récupère une étape par son numéro de séquence"""
        
        statement = (
            select(ShippingRouteStep)
            .where(
                and_(
                    ShippingRouteStep.route_id == route_id,
                    ShippingRouteStep.sequence == sequence,
                    ShippingRouteStep.is_active.is_(True),
                )
            )
        )
        
        result = await session.exec(statement)
        return result.first()
    
    async def get_steps_between_places(
        self,
        session: AsyncSession,
        from_place_id: uuid.UUID,
        to_place_id: uuid.UUID,
    ) -> list[ShippingRouteStep]:
        """Récupère les étapes entre deux lieux"""
        
        statement = (
            select(ShippingRouteStep)
            .where(
                and_(
                    ShippingRouteStep.from_place_id == from_place_id,
                    ShippingRouteStep.to_place_id == to_place_id,
                    ShippingRouteStep.is_active.is_(True),
                )
            )
            .order_by(ShippingRouteStep.sequence.asc())
        )
        
        result = await session.exec(statement)
        return result.all()
    
    async def get_next_sequence_number(
        self,
        session: AsyncSession,
        route_id: uuid.UUID,
    ) -> int:
        """Récupère le prochain numéro de séquence pour une route"""
        
        from sqlmodel import func
        
        statement = (
            select(func.max(ShippingRouteStep.sequence))
            .where(ShippingRouteStep.route_id == route_id)
        )
        
        result = await session.exec(statement)
        max_sequence = result.first()
        
        return (max_sequence or 0) + 1


crud_shipping_route = ShippingRouteCrud(
    model=ShippingRoute,
    schema_create=ShippingRouteCreate,
    schema_update=ShippingRouteUpdate,
    default_filter=and_(
        ShippingRoute.is_active.is_(True),
    ),
    order_by=ShippingRoute.priority.asc(),
)

crud_shipping_route_step = ShippingRouteStepCrud(
    model=ShippingRouteStep,
    schema_create=ShippingRouteStepCreate,
    schema_update=ShippingRouteStepUpdate,
    default_filter=and_(
        ShippingRouteStep.is_active.is_(True),
    ),
    order_by=ShippingRouteStep.sequence.asc(),
)