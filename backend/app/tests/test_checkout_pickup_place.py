"""The pickup point a last-leg option shows at checkout (``pickup_place``).

A pickup route ends where the customer collects the parcel: its destination
place, with the address typed in Logistics → Places. Only physical nodes are
shown — a geographic zone left as destination by an older setup is not an
address the customer can go to.
"""

from app.api.routes.cart import _pickup_place_info
from app.features.place.models import Place
from app.features.shipping.models.route import ShippingRoute


def _route(mode: str, to_place: Place) -> ShippingRoute:
    route = ShippingRoute(
        from_place_id=to_place.id,
        to_place_id=to_place.id,
        name="Retrait",
        mode=mode,
        is_to_customer=True,
        last_leg_delivery_type="pickup",
    )
    route.to_place = to_place
    return route


def test_pickup_route_exposes_its_shop_address() -> None:
    shop = Place(
        name="Boutique Taravao",
        type="shop",
        address_line1="PK 52, route de Taravao",
        address_line2="",
        postal_code="98719",
        city="Taravao",
        country="PF",
    )
    info = _pickup_place_info(_route("pickup", shop))

    assert info is not None
    assert info.place_id == shop.id
    assert info.name == "Boutique Taravao"
    assert info.address_line1 == "PK 52, route de Taravao"
    assert info.address_line2 is None  # blank line → nothing to print
    assert info.postal_code == "98719"
    assert info.city == "Taravao"
    assert info.country == "PF"


def test_pickup_route_without_address_still_names_the_place() -> None:
    warehouse = Place(name="Entrepôt Papeete", type="warehouse", is_warehouse=True)
    info = _pickup_place_info(_route("pickup", warehouse))

    assert info is not None
    assert info.name == "Entrepôt Papeete"
    assert info.address_line1 is None and info.city is None


def test_home_delivery_has_no_pickup_place() -> None:
    island = Place(name="Tahiti", type="island")
    assert _pickup_place_info(_route("road", island)) is None


def test_pickup_route_ending_on_a_zone_shows_nothing() -> None:
    # Older setups put an island as destination: not somewhere to go to.
    island = Place(name="Tahiti", type="island")
    assert _pickup_place_info(_route("pickup", island)) is None
