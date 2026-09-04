from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

from app.features.shipping.models.route import ShippingRoute
from app.features.shipping.services.pricing import (
    CustomsDeclarationFee,
    calculate_shipping_for_routes,
    resolve_billable_weight,
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
    mode: str | None = None,
) -> ShippingRoute:
    return cast(
        ShippingRoute,
        SimpleNamespace(
            id=uuid4(),
            name=name,
            mode=mode,
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


# ---------------------------------------------------------------------------
# resolve_billable_weight
# ---------------------------------------------------------------------------


def test_resolve_billable_weight_uses_actual_when_no_volume() -> None:
    result = resolve_billable_weight(
        Decimal("5"),
        None,
        metadata={},
        mode="air",
    )
    assert result == Decimal("5")


def test_resolve_billable_weight_uses_actual_when_billing_basis_actual_weight() -> None:
    result = resolve_billable_weight(
        Decimal("5"),
        Decimal("0.10"),
        metadata={"billing_basis": "actual_weight"},
        mode="air",
    )
    assert result == Decimal("5")


def test_resolve_billable_weight_air_uses_volumetric_when_heavier() -> None:
    # 0.10 m³ × 167 kg/m³ = 16.7 kg > 5 kg actual
    result = resolve_billable_weight(
        Decimal("5"),
        Decimal("0.10"),
        metadata={},
        mode="air",
    )
    assert result == Decimal("5") or result > Decimal("5")
    assert result == Decimal("0.10") * Decimal("167")


def test_resolve_billable_weight_uses_actual_when_heavier_than_volumetric() -> None:
    # 0.001 m³ × 167 = 0.167 kg < 10 kg actual
    result = resolve_billable_weight(
        Decimal("10"),
        Decimal("0.001"),
        metadata={},
        mode="air",
    )
    assert result == Decimal("10")


def test_resolve_billable_weight_respects_custom_dim_factor() -> None:
    # custom factor 200 kg/m³, 0.05 m³ × 200 = 10 kg > 3 kg actual
    result = resolve_billable_weight(
        Decimal("3"),
        Decimal("0.05"),
        metadata={"dim_factor_kg_per_m3": "200"},
        mode="air",
    )
    assert result == Decimal("0.05") * Decimal("200")


def test_resolve_billable_weight_sea_default_factor() -> None:
    # sea default 1000 kg/m³, 0.05 m³ × 1000 = 50 kg > 5 kg actual
    result = resolve_billable_weight(
        Decimal("5"),
        Decimal("0.05"),
        metadata={},
        mode="sea",
    )
    assert result == Decimal("0.05") * Decimal("1000")


def test_calculate_shipping_uses_volumetric_weight_when_heavier() -> None:
    # 0.10 m³ × 167 (air default) = 16.7 kg — heavier than 2 kg actual.
    # Route: 500/kg → fee = 500 × 16.7 = 8350
    air_route = _route(base_price="0", price_per_kg="500", mode="air")

    summary = calculate_shipping_for_routes(
        routes=[air_route],
        total_weight_kg=Decimal("2"),
        total_volume_m3=Decimal("0.10"),
        declared_value=Decimal("0"),
        currency="XPF",
    )

    assert summary.total_fee == Decimal("8350")
    assert summary.breakdown[0].billable_weight == Decimal("16.7")


def test_calculate_shipping_falls_back_to_actual_when_no_volume() -> None:
    route = _route(base_price="0", price_per_kg="500")

    summary = calculate_shipping_for_routes(
        routes=[route],
        total_weight_kg=Decimal("2"),
        total_volume_m3=None,
        declared_value=Decimal("0"),
        currency="XPF",
    )

    assert summary.total_fee == Decimal("1000")


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


# ---------------------------------------------------------------------------
# Per-declaration customs fees (audit item F3)
# ---------------------------------------------------------------------------


def _declaration_fee(amount: str, *, name: str = "Papeete") -> CustomsDeclarationFee:
    return CustomsDeclarationFee(
        place_id=uuid4(), place_name=name, amount=Decimal(amount)
    )


def test_customs_declaration_fee_is_added_once_to_the_total() -> None:
    france_to_papeete = _route(base_price="1000", price_per_kg="2000")
    papeete_to_home = _route(base_price="500", price_per_kg="0")

    summary = calculate_shipping_for_routes(
        routes=[france_to_papeete, papeete_to_home],
        total_weight_kg=Decimal("2"),
        declared_value=Decimal("100000"),
        currency="XPF",
        customs_declaration_fees=[_declaration_fee("3500")],
    )

    # 1000 + 2000×2 + 500 = 5500 de transport, + 3500 de déclaration.
    assert summary.total_fee == Decimal("9000")
    assert len(summary.customs_declaration_fees) == 1
    assert summary.customs_declaration_fees[0].amount == Decimal("3500")


def test_customs_declaration_fee_does_not_scale_with_weight_or_value() -> None:
    """Per declaration means per shipment: a bigger cart pays the same fee."""
    route = _route(base_price="0", price_per_kg="0")
    fee = _declaration_fee("3500")

    small = calculate_shipping_for_routes(
        routes=[route],
        total_weight_kg=Decimal("1"),
        declared_value=Decimal("50000"),
        currency="XPF",
        customs_declaration_fees=[fee],
    )
    large = calculate_shipping_for_routes(
        routes=[route],
        total_weight_kg=Decimal("40"),
        declared_value=Decimal("2000000"),
        currency="XPF",
        customs_declaration_fees=[fee],
    )

    assert small.total_fee == large.total_fee == Decimal("3500")


def test_customs_declaration_fees_are_billed_without_any_route() -> None:
    """Goods still clear customs when no leg is billed to the customer (F6)."""
    summary = calculate_shipping_for_routes(
        routes=[],
        total_weight_kg=Decimal("2"),
        declared_value=Decimal("100000"),
        currency="XPF",
        customs_declaration_fees=[_declaration_fee("3500")],
    )

    assert summary.total_fee == Decimal("3500")
    assert summary.breakdown == []


def test_non_positive_customs_declaration_fees_are_dropped() -> None:
    summary = calculate_shipping_for_routes(
        routes=[],
        total_weight_kg=Decimal("2"),
        declared_value=Decimal("100000"),
        currency="XPF",
        customs_declaration_fees=[_declaration_fee("0")],
    )

    assert summary.total_fee == Decimal("0")
    assert summary.customs_declaration_fees == ()


def test_serialize_shipping_cost_summary_keeps_declaration_fees_auditable() -> None:
    fee = _declaration_fee("3500")
    summary = calculate_shipping_for_routes(
        routes=[_route(base_price="500", price_per_kg="0")],
        total_weight_kg=Decimal("2"),
        declared_value=Decimal("100000"),
        currency="XPF",
        customs_declaration_fees=[fee],
    )

    payload = serialize_shipping_cost_summary(summary)

    assert payload["customs_declaration_fees"] == [
        {
            "place_id": str(fee.place_id),
            "place_name": "Papeete",
            "amount": "3500",
        }
    ]
