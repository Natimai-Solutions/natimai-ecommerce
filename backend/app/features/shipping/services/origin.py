"""Where goods come from, and what that implies: customs and routing.

Two facts are read from the database, never from address text:

* the **main warehouse** (``Place.is_main_warehouse``) — supplier goods
  converge there, the last leg to the customer starts there;
* the **customs regime** of an origin place — a supplier in the same country
  as the main warehouse is *domestic* (no customs, no import freight); one in
  another country is *import*, unless that country is listed in the
  ``customs_free_countries`` system setting (free-trade area, same customs
  territory…) or the place carries an explicit ``customs_regime`` override.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.place.models import Place
from app.features.product.models.product import Product
from app.features.shipping.models.route import ShippingRoute

CUSTOMS_FREE_COUNTRIES_KEY = "customs_free_countries"
CUSTOMS_FREE_COUNTRIES_DESCRIPTION = (
    "Codes pays ISO (séparés par des virgules) dont les fournisseurs sont "
    "traités comme locaux : ni douane ni fret d'import dans le prix, même "
    "s'ils ne sont pas dans le pays de l'entrepôt principal (ex. union "
    "douanière). Vide = seul le pays de l'entrepôt principal est local."
)

CUSTOMS_REGIME_DOMESTIC = "domestic"
CUSTOMS_REGIME_IMPORT = "import"
CUSTOMS_REGIMES: tuple[str, ...] = (CUSTOMS_REGIME_DOMESTIC, CUSTOMS_REGIME_IMPORT)


class OriginRegime(str, Enum):
    """Customs regime of an origin, as it drives pricing."""

    DOMESTIC = "domestic"  # no customs rate, no import freight in the price
    IMPORT = "import"  # CAF base: freight + insurance, then customs
    UNKNOWN = "unknown"  # origin not configured → legacy behaviour (import)

    @property
    def applies_customs(self) -> bool:
        """Customs and import freight enter the price unless clearly domestic."""
        return self is not OriginRegime.DOMESTIC


def parse_country_list(raw: str | None) -> frozenset[str]:
    """``"FR, de ,,it"`` → ``{"FR", "DE", "IT"}``."""
    if not raw:
        return frozenset()
    return frozenset(part.strip().upper() for part in raw.split(",") if part.strip())


async def load_customs_free_countries(session: AsyncSession) -> frozenset[str]:
    """Countries whose suppliers count as domestic (system setting)."""
    from app.core import runtime_settings

    return frozenset(await runtime_settings.get(CUSTOMS_FREE_COUNTRIES_KEY, session))


async def get_main_warehouse(session: AsyncSession) -> Place | None:
    """The place flagged ``is_main_warehouse``.

    Falls back, for deployments that have not flagged one yet, to the
    destination of the default import corridor, then to the first active
    warehouse — the historical heuristics.
    """
    flagged = (
        await session.exec(
            select(Place).where(
                col(Place.is_main_warehouse).is_(True),
                col(Place.is_active).is_(True),
            )
        )
    ).first()
    if flagged is not None:
        return flagged

    import_route = (
        await session.exec(
            select(ShippingRoute)
            .where(
                col(ShippingRoute.is_default_import).is_(True),
                col(ShippingRoute.is_active).is_(True),
            )
            .limit(1)
        )
    ).first()
    if import_route is not None:
        destination = await session.get(Place, import_route.to_place_id)
        if destination is not None:
            return destination

    return (
        await session.exec(
            select(Place)
            .where(col(Place.is_warehouse).is_(True), col(Place.is_active).is_(True))
            .order_by(col(Place.name).asc())
            .limit(1)
        )
    ).first()


async def set_main_warehouse(session: AsyncSession, place_id: uuid.UUID) -> Place:
    """Flag ``place_id`` as the main warehouse, unflagging any other (no commit)."""
    place = await session.get(Place, place_id)
    if place is None:
        raise LookupError(str(place_id))
    others = await session.exec(
        select(Place).where(
            col(Place.is_main_warehouse).is_(True), col(Place.id) != place_id
        )
    )
    for other in others.all():
        other.is_main_warehouse = False
        session.add(other)
    await session.flush()  # the partial unique index sees the unflag first
    place.is_main_warehouse = True
    place.is_warehouse = True
    session.add(place)
    return place


def resolve_origin_regime(
    origin: Place | None,
    main_warehouse: Place | None,
    *,
    free_countries: frozenset[str] = frozenset(),
) -> OriginRegime:
    """Customs regime of an origin place against the main warehouse.

    Order: explicit override on the origin → same country as the main
    warehouse (or a country listed as customs-free) → import. Unknown when
    the origin or the countries are not configured: the price then keeps the
    historical behaviour (customs apply), which errs on the visible side.
    """
    if origin is None:
        return OriginRegime.UNKNOWN
    override = (origin.customs_regime or "").strip().lower()
    if override == CUSTOMS_REGIME_DOMESTIC:
        return OriginRegime.DOMESTIC
    if override == CUSTOMS_REGIME_IMPORT:
        return OriginRegime.IMPORT

    origin_country = (origin.country or "").strip().upper()
    if not origin_country:
        return OriginRegime.UNKNOWN
    if origin_country in free_countries:
        return OriginRegime.DOMESTIC
    main_country = (
        (main_warehouse.country or "").strip().upper() if main_warehouse else ""
    )
    if not main_country:
        return OriginRegime.UNKNOWN
    return (
        OriginRegime.DOMESTIC if origin_country == main_country else OriginRegime.IMPORT
    )


@dataclass(frozen=True)
class OriginContext:
    """What every origin is compared against; load once per request/loop."""

    main_warehouse: Place | None
    free_countries: frozenset[str]


async def load_origin_context(session: AsyncSession) -> OriginContext:
    """Main warehouse + customs-free countries, for batch pricing."""
    return OriginContext(
        main_warehouse=await get_main_warehouse(session),
        free_countries=await load_customs_free_countries(session),
    )


async def resolve_product_origin_regime(
    session: AsyncSession,
    product: Product,
    *,
    context: OriginContext | None = None,
) -> OriginRegime:
    """Regime of a product from its supplier origin place (``supplier_place_id``).

    Pass ``context`` when pricing many products: it spares one main-warehouse
    and one setting query per product.
    """
    origin_id = getattr(product, "supplier_place_id", None)
    if origin_id is None:
        return OriginRegime.UNKNOWN
    origin = await session.get(Place, origin_id)
    if origin is None:
        return OriginRegime.UNKNOWN
    if (origin.customs_regime or "").strip().lower() in CUSTOMS_REGIMES:
        return resolve_origin_regime(origin, None)
    if context is None:
        context = await load_origin_context(session)
    return resolve_origin_regime(
        origin, context.main_warehouse, free_countries=context.free_countries
    )
