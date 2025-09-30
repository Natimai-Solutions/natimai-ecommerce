"""
CRUD for physical places (airports, ports, warehouses, addresses...).
"""

import uuid

from sqlmodel import and_, or_, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.place.models import (
    Place,
    PlaceCreate,
    PlaceUpdate,
)


class PlaceCrud(CrudBase[Place, PlaceCreate, PlaceUpdate]):
    async def get_by_code(
        self,
        session: AsyncSession,
        code: str,
    ) -> Place | None:
        """Retrieve a place by its code"""
        statement = select(Place).where(
            Place.code == code,
            Place.is_active.is_(True),
        )

        result = await session.exec(statement)
        return result.first()

    async def get_by_type(
        self,
        session: AsyncSession,
        place_type: str,
        country: str | None = None,
    ) -> list[Place]:
        """Retrieve places by type"""

        conditions = [
            Place.type == place_type,
            Place.is_active.is_(True),
        ]

        if country:
            conditions.append(Place.country == country)

        statement = select(Place).where(and_(*conditions)).order_by(Place.name.asc())

        result = await session.exec(statement)
        return result.all()

    async def get_warehouses(
        self,
        session: AsyncSession,
        country: str | None = None,
        with_service: str | None = None,
    ) -> list[Place]:
        """Récupère les entrepôts"""

        conditions = [
            Place.is_warehouse.is_(True),
            Place.is_active.is_(True),
        ]

        if country:
            conditions.append(Place.country == country)

        # Filtres par service
        if with_service == "customs":
            conditions.append(Place.customs_clearance.is_(True))
        elif with_service == "consolidation":
            conditions.append(Place.consolidation_service.is_(True))
        elif with_service == "repackaging":
            conditions.append(Place.repackaging_service.is_(True))

        statement = select(Place).where(and_(*conditions)).order_by(Place.name.asc())

        result = await session.exec(statement)
        return result.all()

    async def get_by_country(
        self,
        session: AsyncSession,
        country_code: str,
        place_type: str | None = None,
    ) -> list[Place]:
        """Récupère les lieux d'un pays"""

        conditions = [
            Place.country == country_code,
            Place.is_active.is_(True),
        ]

        if place_type:
            conditions.append(Place.type == place_type)

        statement = select(Place).where(and_(*conditions)).order_by(Place.name.asc())

        result = await session.exec(statement)
        return result.all()

    async def search_places(
        self,
        session: AsyncSession,
        search_term: str,
        place_type: str | None = None,
        country: str | None = None,
    ) -> list[Place]:
        """Recherche de lieux par nom, code ou adresse"""

        conditions = [Place.is_active.is_(True)]

        if place_type:
            conditions.append(Place.type == place_type)

        if country:
            conditions.append(Place.country == country)

        # Search in different fields
        search_conditions = [
            Place.name.ilike(f"%{search_term}%"),
            Place.code.ilike(f"%{search_term}%"),
            Place.city.ilike(f"%{search_term}%"),
            Place.address_line1.ilike(f"%{search_term}%"),
        ]

        statement = (
            select(Place)
            .where(and_(*conditions, or_(*search_conditions)))
            .order_by(Place.name.asc())
        )

        result = await session.exec(statement)
        return result.all()

    async def get_nearest_places(
        self,
        session: AsyncSession,
        latitude: float,
        longitude: float,
        max_distance_km: float | None = None,
        place_type: str | None = None,
        limit: int = 10,
    ) -> list[Place]:
        """
        Récupère les lieux les plus proches d'une position
        Note: Pour une implémentation complète, utiliser PostGIS
        """

        conditions = [
            Place.is_active.is_(True),
            Place.latitude.is_not(None),
            Place.longitude.is_not(None),
        ]

        if place_type:
            conditions.append(Place.type == place_type)

        # Filtre approximatif par distance (carré au lieu de cercle)
        if max_distance_km:
            # Approximation: 1 degré ≈ 111 km
            degree_range = max_distance_km / 111.0
            conditions.extend(
                [
                    Place.latitude.between(
                        latitude - degree_range, latitude + degree_range
                    ),
                    Place.longitude.between(
                        longitude - degree_range, longitude + degree_range
                    ),
                ]
            )

        statement = (
            select(Place)
            .where(and_(*conditions))
            # Tri approximatif par distance (somme des différences absolues)
            .order_by(
                (
                    abs(Place.latitude - latitude) + abs(Place.longitude - longitude)
                ).asc()
            )
            .limit(limit)
        )

        result = await session.exec(statement)
        return result.all()

    async def get_capacity_info(
        self,
        session: AsyncSession,
        place_id: uuid.UUID,
    ) -> dict:
        """Récupère les informations de capacité d'un entrepôt"""

        place = await self.read(session, id=place_id)
        if not place or not place.is_warehouse:
            return {}

        capacity_info = {
            "place_id": place_id,
            "current_capacity_m3": place.current_capacity_m3 or 0,
            "max_capacity_m3": place.max_capacity_m3,
            "utilization_percentage": 0.0,
            "available_capacity_m3": 0,
            "is_full": False,
        }

        if place.max_capacity_m3 and place.max_capacity_m3 > 0:
            current = place.current_capacity_m3 or 0
            capacity_info["utilization_percentage"] = (
                current / place.max_capacity_m3
            ) * 100
            capacity_info["available_capacity_m3"] = place.max_capacity_m3 - current
            capacity_info["is_full"] = current >= place.max_capacity_m3

        return capacity_info

    async def update_capacity(
        self,
        session: AsyncSession,
        place_id: uuid.UUID,
        capacity_change_m3: float,
    ) -> Place | None:
        """Met à jour la capacité actuelle d'un entrepôt"""

        place = await self.read(session, id=place_id)
        if not place or not place.is_warehouse:
            return None

        new_capacity = (place.current_capacity_m3 or 0) + capacity_change_m3

        # S'assurer que la capacité ne devient pas négative
        if new_capacity < 0:
            new_capacity = 0

        updated_place = await self.update(
            session, db_obj=place, obj_in={"current_capacity_m3": new_capacity}
        )

        return updated_place


crud_place = PlaceCrud(
    model=Place,
    schema_create=PlaceCreate,
    schema_update=PlaceUpdate,
    default_filter=and_(
        Place.is_active.is_(True),
    ),
    order_by=Place.name.asc(),
)

