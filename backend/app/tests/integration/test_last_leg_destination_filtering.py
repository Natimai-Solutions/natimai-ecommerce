"""Integration tests: last-leg delivery modes filtered by customer destination.

Covers the destination-aware resolution chain:
- place hierarchy (île → archipel → pays) and ancestor chain,
- postal-code → island deduction,
- served-zone matching (a route serving an archipelago covers its islands),
- always_available routes (in-store pickup) visible everywhere,
- legacy unscoped routes (no served zone) still visible everywhere,
- specificity: an island-specific route beats an archipelago-wide one.
"""

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.cart import _resolve_last_leg_route
from app.features.place.crud import crud_place
from app.features.place.models import Place, PlacePostalCode, PlaceTreeNode
from app.features.shipping.models.route import ShippingRoute
from app.features.shipping.models.route_served_place import RouteServedPlace
from app.features.shipping.services.last_leg import resolve_last_leg_candidates


async def _seed_pf_tree(session: AsyncSession) -> dict[str, Place]:
    """PF → Société (archipel) → [Tahiti, Moorea] + un entrepôt de départ."""
    country = Place(name="Polynésie française", type="country", country="PF")
    session.add(country)
    await session.flush()
    societe = Place(
        name="Archipel de la Société", type="region", country="PF", parent_id=country.id
    )
    session.add(societe)
    await session.flush()
    tahiti = Place(name="Tahiti", type="island", country="PF", parent_id=societe.id)
    moorea = Place(name="Moorea", type="island", country="PF", parent_id=societe.id)
    warehouse = Place(name="Entrepôt Papeete", type="warehouse", is_warehouse=True)
    session.add_all([tahiti, moorea, warehouse])
    await session.flush()
    session.add(PlacePostalCode(place_id=moorea.id, country="PF", postal_code="98728"))
    await session.flush()
    return {
        "country": country,
        "societe": societe,
        "tahiti": tahiti,
        "moorea": moorea,
        "warehouse": warehouse,
    }


def _last_leg_route(
    places: dict[str, Place],
    *,
    name: str,
    delivery_type: str,
    always_available: bool = False,
    priority: int = 0,
) -> ShippingRoute:
    return ShippingRoute(
        from_place_id=places["warehouse"].id,
        to_place_id=places["country"].id,
        name=name,
        mode="road",
        is_to_customer=True,
        last_leg_delivery_type=delivery_type,
        always_available=always_available,
        priority=priority,
    )


@pytest.mark.asyncio
async def test_ancestor_chain_and_postal_resolution(
    db_session: AsyncSession,
) -> None:
    places = await _seed_pf_tree(db_session)

    resolved = await crud_place.resolve_by_postal_code(
        db_session, country="pf", postal_code=" 98728 "
    )
    assert resolved is not None and resolved.id == places["moorea"].id

    chain = await crud_place.get_ancestor_chain(db_session, place_id=resolved.id)
    assert [p.id for p in chain] == [
        places["moorea"].id,
        places["societe"].id,
        places["country"].id,
    ]

    unknown = await crud_place.resolve_by_postal_code(
        db_session, country="PF", postal_code="99999"
    )
    assert unknown is None


@pytest.mark.asyncio
async def test_postal_code_directory_by_country(db_session: AsyncSession) -> None:
    places = await _seed_pf_tree(db_session)
    db_session.add(
        PlacePostalCode(place_id=places["tahiti"].id, country="PF", postal_code="98714")
    )
    await db_session.flush()

    rows = await crud_place.list_postal_codes_by_country(db_session, country="pf")
    directory = {code.postal_code: place.name for code, place in rows}
    assert directory == {"98714": "Tahiti", "98728": "Moorea"}
    # Sorted by postal code for a stable dropdown.
    assert [code.postal_code for code, _ in rows] == ["98714", "98728"]


@pytest.mark.asyncio
async def test_geo_tree_excludes_operational_nodes(db_session: AsyncSession) -> None:
    places = await _seed_pf_tree(db_session)
    roots = await crud_place.get_geo_tree(db_session, country="PF")

    tree_ids = set()

    def collect(nodes: list[PlaceTreeNode]) -> None:
        for node in nodes:
            tree_ids.add(node.id)
            collect(node.children)

    collect(roots)
    assert places["country"].id in tree_ids
    assert places["moorea"].id in tree_ids
    assert places["warehouse"].id not in tree_ids

    country_node = next(n for n in roots if n.id == places["country"].id)
    societe_node = next(
        c for c in country_node.children if c.id == places["societe"].id
    )
    assert {c.id for c in societe_node.children} == {
        places["tahiti"].id,
        places["moorea"].id,
    }


@pytest.mark.asyncio
async def test_served_zone_filtering_and_always_available(
    db_session: AsyncSession,
) -> None:
    places = await _seed_pf_tree(db_session)

    boat = _last_leg_route(
        places, name="Fret bateau Société", delivery_type="sea_freight"
    )
    pickup = _last_leg_route(
        places, name="Retrait boutique", delivery_type="pickup", always_available=True
    )
    legacy = _last_leg_route(
        places, name="Domicile (non scopé)", delivery_type="home_delivery"
    )
    tahiti_only = _last_leg_route(
        places, name="Coursier Tahiti", delivery_type="courier"
    )
    db_session.add_all([boat, pickup, legacy, tahiti_only])
    await db_session.flush()
    db_session.add_all(
        [
            # le bateau dessert l'archipel entier → couvre Moorea par héritage
            RouteServedPlace(route_id=boat.id, place_id=places["societe"].id),
            # le coursier ne dessert que Tahiti
            RouteServedPlace(route_id=tahiti_only.id, place_id=places["tahiti"].id),
        ]
    )
    await db_session.flush()

    moorea_chain = [
        places["moorea"].id,
        places["societe"].id,
        places["country"].id,
    ]
    candidates = await resolve_last_leg_candidates(
        db_session, destination_chain=moorea_chain
    )
    # Moorea : bateau (archipel), pickup (toujours), domicile (legacy non scopé),
    # mais PAS le coursier Tahiti.
    assert set(candidates) == {"sea_freight", "pickup", "home_delivery"}

    # Destination inconnue (adresse sans zone) : uniquement pickup + legacy.
    candidates_nowhere = await resolve_last_leg_candidates(
        db_session, destination_chain=[]
    )
    assert set(candidates_nowhere) == {"pickup", "home_delivery"}

    # Le checkout rejette le mode non desservi via la résolution → None.
    resolved = await _resolve_last_leg_route(
        db_session, delivery_type="courier", destination_chain=moorea_chain
    )
    assert resolved is None


@pytest.mark.asyncio
async def test_island_specific_route_beats_archipelago_route(
    db_session: AsyncSession,
) -> None:
    places = await _seed_pf_tree(db_session)

    generic = _last_leg_route(
        places,
        name="Bateau Société (générique)",
        delivery_type="sea_freight",
        priority=0,
    )
    moorea_special = _last_leg_route(
        places,
        name="Bateau Moorea (spécifique)",
        delivery_type="sea_freight",
        priority=99,
    )
    db_session.add_all([generic, moorea_special])
    await db_session.flush()
    db_session.add_all(
        [
            RouteServedPlace(route_id=generic.id, place_id=places["societe"].id),
            RouteServedPlace(route_id=moorea_special.id, place_id=places["moorea"].id),
        ]
    )
    await db_session.flush()

    moorea_chain = [
        places["moorea"].id,
        places["societe"].id,
        places["country"].id,
    ]
    candidates = await resolve_last_leg_candidates(
        db_session, destination_chain=moorea_chain
    )
    # Malgré une priority moins bonne, la route la plus spécifique gagne.
    assert candidates["sea_freight"].route.id == moorea_special.id

    tahiti_chain = [
        places["tahiti"].id,
        places["societe"].id,
        places["country"].id,
    ]
    candidates_tahiti = await resolve_last_leg_candidates(
        db_session, destination_chain=tahiti_chain
    )
    assert candidates_tahiti["sea_freight"].route.id == generic.id
