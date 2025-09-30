"""
CRUD for partners (clients and suppliers).
"""


from sqlmodel import and_, or_, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.partner.models import (
    Partner,
    PartnerCreate,
    PartnerUpdate,
)


class PartnerCrud(CrudBase[Partner, PartnerCreate, PartnerUpdate]):
    async def get_by_email(
        self,
        session: AsyncSession,
        email: str,
    ) -> Partner | None:
        """Retrieve a partner by email"""
        statement = select(Partner).where(
            Partner.email == email,
            Partner.is_active.is_(True),
        )

        result = await session.exec(statement)
        return result.first()

    async def search_partners(
        self,
        session: AsyncSession,
        search_term: str,
    ) -> list[Partner]:
        """Search for partners by name, email or city"""

        conditions = [Partner.is_active.is_(True)]

        # Search in different fields
        search_conditions = [
            Partner.name.ilike(f"%{search_term}%"),
            Partner.email.ilike(f"%{search_term}%"),
            Partner.city.ilike(f"%{search_term}%"),
            Partner.phone.ilike(f"%{search_term}%"),
        ]

        statement = (
            select(Partner)
            .where(and_(*conditions, or_(*search_conditions)))
            .order_by(Partner.name.asc())
        )

        result = await session.exec(statement)
        return result.all()

    async def get_by_country(
        self,
        session: AsyncSession,
        country_code: str,
    ) -> list[Partner]:
        """Récupère les partenaires d'un pays"""

        statement = (
            select(Partner)
            .where(
                and_(
                    Partner.country == country_code,
                    Partner.is_active.is_(True),
                )
            )
            .order_by(Partner.name.asc())
        )

        result = await session.exec(statement)
        return result.all()

    async def get_partners_with_routes(
        self,
        session: AsyncSession,
        is_origin: bool = True,
    ) -> list[Partner]:
        """Récupère les partenaires ayant des routes (comme origine ou destination)"""

        from app.features.shipping.models.shipping_route import ShippingRoute

        if is_origin:
            join_condition = ShippingRoute.from_partner_id == Partner.id
        else:
            join_condition = ShippingRoute.to_partner_id == Partner.id

        statement = (
            select(Partner)
            .join(ShippingRoute, join_condition)
            .where(Partner.is_active.is_(True))
            .distinct()
            .order_by(Partner.name.asc())
        )

        result = await session.exec(statement)
        return result.all()


crud_partner = PartnerCrud(
    model=Partner,
    schema_create=PartnerCreate,
    schema_update=PartnerUpdate,
    default_filter=and_(
        Partner.is_active.is_(True),
    ),
    order_by=Partner.name.asc(),
)

