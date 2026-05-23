from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

from app.features.shipping.models.route import ShippingRoute
from app.features.shipping.services.pricing import (
    calculate_shipping_for_routes,
    serialize_shipping_cost_summary,
)


def _route(
    *,
    base_price: str,
    price_per_kg: str,
    route_metadata: dict[str, Any] | None = None,
    eta_days: int | None = None,
    carbon: float | None = None,
    name: str | None = None,
) -> ShippingRoute:
    return cast(
        ShippingRoute,
        SimpleNamespace(
            id=uuid4(),
            name=name,
            base_price=Decimal(base_price),
            price_per_kg=Decimal(price_per_kg),
            route_metadata=route_metadata,
            eta_days=eta_days,
            carbon_footprint_kg_co2e=carbon,
        ),
    )


def test_calculate_shipping_for_routes_client_tahiti_path() -> None:
    france_to_papeete_air = _route(
        base_price="1000",
        price_per_kg="2000",
        eta_days=3,
        carbon=40.0,
    )
    papeete_to_home = _route(
        base_price="500",
        price_per_kg="0",
        eta_days=1,
        carbon=1.5,
    )

    summary = calculate_shipping_for_routes(
        routes=[france_to_papeete_air, papeete_to_home],
        total_weight_kg=Decimal("2"),
        declared_value=Decimal("100000"),
        currency="XPF",
    )

    assert summary.total_fee == Decimal("5500")
    assert len(summary.breakdown) == 2
    assert summary.eta_days == 4
    assert summary.carbon_footprint_kg_co2e == 41.5


def test_calculate_shipping_for_routes_client_arutua_path() -> None:
    france_to_papeete_boat = _route(
        base_price="0",
        price_per_kg="500",
        route_metadata={"value_percent": "1"},
        eta_days=10,
        carbon=8.0,
    )
    papeete_to_arutua_air_tahiti = _route(
        base_price="0",
        price_per_kg="100",
        eta_days=1,
        carbon=3.0,
    )

    summary = calculate_shipping_for_routes(
        routes=[france_to_papeete_boat, papeete_to_arutua_air_tahiti],
        total_weight_kg=Decimal("2"),
        declared_value=Decimal("10000"),
        currency="XPF",
    )

    # Route 1: 500*2 + 1%*10000 = 1100
    # Route 2: 100*2 = 200
    assert summary.total_fee == Decimal("1300")
    assert len(summary.breakdown) == 2
    assert summary.eta_days == 11
    assert summary.carbon_footprint_kg_co2e == 11.0


def test_calculate_shipping_for_routes_supports_lb_weight_pricing_unit() -> None:
    route_priced_in_lb = _route(
        base_price="0",
        price_per_kg="100",
        route_metadata={"weight_unit": "lb"},
    )

    summary = calculate_shipping_for_routes(
        routes=[route_priced_in_lb],
        total_weight_kg=Decimal("1"),
        declared_value=Decimal("0"),
        currency="EUR",
    )

    assert summary.total_fee == Decimal("220.46")


def test_calculate_shipping_ignores_expired_tariff_extras() -> None:
    route_with_expired_value_rate = _route(
        base_price="0",
        price_per_kg="500",
        route_metadata={
            "value_percent": "1",
            "min_total": "5000",
            "effective_from": "2020-01-01",
            "effective_until": "2020-12-31",
        },
    )

    as_of = datetime(2026, 5, 11, tzinfo=timezone.utc)
    summary = calculate_shipping_for_routes(
        routes=[route_with_expired_value_rate],
        total_weight_kg=Decimal("2"),
        declared_value=Decimal("10000"),
        currency="XPF",
        as_of=as_of,
    )

    # value_percent / min_total are outside their effective window: only base columns apply.
    assert summary.total_fee == Decimal("1000")
    assert summary.breakdown[0].pricing_effective is False
    assert summary.breakdown[0].value_fee == Decimal("0")


def test_calculate_shipping_applies_tariff_inside_effective_window() -> None:
    route_with_current_value_rate = _route(
        base_price="0",
        price_per_kg="500",
        route_metadata={
            "value_percent": "1",
            "effective_from": "2026-01-01",
            "effective_until": "2026-12-31",
        },
    )

    summary = calculate_shipping_for_routes(
        routes=[route_with_current_value_rate],
        total_weight_kg=Decimal("2"),
        declared_value=Decimal("10000"),
        currency="XPF",
        as_of=datetime(2026, 5, 11, tzinfo=timezone.utc),
    )

    assert summary.total_fee == Decimal("1100")
    assert summary.breakdown[0].pricing_effective is True


def test_serialize_shipping_cost_summary_is_json_safe() -> None:
    route = _route(base_price="1000", price_per_kg="2000", eta_days=3, name="FR->PPT")
    summary = calculate_shipping_for_routes(
        routes=[route],
        total_weight_kg=Decimal("2"),
        declared_value=Decimal("0"),
        currency="XPF",
    )

    payload = serialize_shipping_cost_summary(summary)

    import json

    json.dumps(payload)  # must not raise
    assert payload["currency"] == "XPF"
    assert payload["total_fee"] == "5000"
    assert payload["segments"][0]["route_name"] == "FR->PPT"
    assert payload["segments"][0]["total_fee"] == "5000"
