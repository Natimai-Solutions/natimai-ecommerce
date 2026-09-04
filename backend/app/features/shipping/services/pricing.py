from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from app.features.shipping.models.route import ShippingRoute
from app.utils.money import quantize_amount

_LB_PER_KG = Decimal("2.2046226218")
_SUPPORTED_WEIGHT_UNITS = {"kg", "lb"}

# Default dimensional-weight factors (kg/m³) by transport mode.
# Standard IATA for air; W/M (1 cbm = 1000 kg) for sea/road.
# Override per-route via route_metadata["dim_factor_kg_per_m3"].
_DEFAULT_DIM_FACTOR_AIR = Decimal("167")
_DEFAULT_DIM_FACTOR_SEA = Decimal("1000")


@dataclass(frozen=True)
class RouteShippingCostBreakdown:
    """Represents route shipping cost breakdown."""

    route_id: uuid.UUID
    route_name: str | None
    fixed_fee: Decimal
    weight_fee: Decimal
    value_fee: Decimal
    total_fee: Decimal
    weight_unit: str
    billable_weight: Decimal
    eta_days: int | None
    carbon_footprint_kg_co2e: float | None
    pricing_effective: bool


@dataclass(frozen=True)
class CustomsDeclarationFee:
    """Fixed charges owed once per customs declaration.

    Redevances, participations and forwarder file fees are billed per
    declaration, never per article: spreading them over the lines would make
    the unit price wrong in both directions depending on cart size (audit item
    F3). They are carried by the customs ``Place``, not by the route, so
    several corridors clearing at the same border still mean one declaration.
    """

    place_id: uuid.UUID
    place_name: str | None
    amount: Decimal


@dataclass(frozen=True)
class ShippingCostSummary:
    """Represents shipping cost summary."""

    total_fee: Decimal
    currency: str
    breakdown: list[RouteShippingCostBreakdown]
    eta_days: int | None
    carbon_footprint_kg_co2e: float | None
    customs_declaration_fees: tuple[CustomsDeclarationFee, ...] = ()


def _to_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    """Execute to decimal."""
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default


def _route_metadata_to_dict(route: ShippingRoute) -> dict[str, Any]:
    """Execute route metadata to dict."""
    raw_metadata = route.route_metadata
    if raw_metadata is None:
        return {}

    if isinstance(raw_metadata, dict):
        return raw_metadata

    if isinstance(raw_metadata, str):
        try:
            parsed = json.loads(raw_metadata)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return parsed

    return {}


def _resolve_weight_unit(metadata: dict[str, Any]) -> str:
    """Execute resolve weight unit."""
    candidate = str(metadata.get("weight_unit", "kg")).strip().lower()
    if candidate not in _SUPPORTED_WEIGHT_UNITS:
        return "kg"
    return candidate


def _convert_weight_from_kg(weight_kg: Decimal, target_unit: str) -> Decimal:
    """Convert weight from kg."""
    if target_unit == "lb":
        return weight_kg * _LB_PER_KG
    return weight_kg


def _extract_value_rate(metadata: dict[str, Any]) -> Decimal:
    """Execute extract value rate."""
    if "value_rate" in metadata:
        return max(_to_decimal(metadata.get("value_rate")), Decimal("0"))

    if "price_per_value_rate" in metadata:
        return max(_to_decimal(metadata.get("price_per_value_rate")), Decimal("0"))

    if "value_percent" in metadata:
        percent = _to_decimal(metadata.get("value_percent"))
        return max(percent / Decimal("100"), Decimal("0"))

    if "price_per_value_percent" in metadata:
        percent = _to_decimal(metadata.get("price_per_value_percent"))
        return max(percent / Decimal("100"), Decimal("0"))

    return Decimal("0")


def _extract_bound(metadata: dict[str, Any], key: str) -> Decimal | None:
    """Execute extract bound."""
    if key not in metadata:
        return None
    value = _to_decimal(metadata.get(key), Decimal("-1"))
    if value < 0:
        return None
    return value


def _parse_effective_date(value: Any) -> datetime | None:
    """Parse effective date."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        normalized = text.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            try:
                parsed = datetime.fromisoformat(f"{normalized}T00:00:00")
            except ValueError:
                return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _is_pricing_window_effective(
    metadata: dict[str, Any],
    as_of: datetime,
) -> bool:
    """A route tariff is effective when ``as_of`` falls inside its optional window.

    ``route_metadata`` may carry ``effective_from`` / ``effective_until`` (ISO date
    or datetime strings). Absent bounds mean "always effective". When the tariff is
    not effective the metadata-driven extras (value rate, min, max) are not applied.
    """

    effective_from = _parse_effective_date(
        metadata.get("effective_from", metadata.get("pricing_effective_from"))
    )
    effective_until = _parse_effective_date(
        metadata.get("effective_until", metadata.get("pricing_effective_until"))
    )

    if effective_from is not None and as_of < effective_from:
        return False
    if effective_until is not None and as_of > effective_until:
        return False
    return True


def resolve_billable_weight(
    weight_kg: Decimal,
    volume_m3: Decimal | None,
    *,
    metadata: dict[str, Any],
    mode: str | None = None,
) -> Decimal:
    """Return the billable weight for a single route (kg basis, before unit conversion).

    Strategy is driven by ``route_metadata["billing_basis"]``:
    - ``volumetric_max`` (default when volume is available): max(actual, volumetric).
    - ``actual_weight``  : always use actual weight regardless of volume.

    When ``volume_m3`` is None (missing or incomplete product dimensions) the
    function always falls back to the actual weight.

    The dimensional factor ``dim_factor_kg_per_m3`` is read from ``route_metadata``
    and defaults to 167 (air) or 1000 (sea/other) based on the route ``mode``.
    """
    actual = max(weight_kg, Decimal("0"))

    billing_basis = str(metadata.get("billing_basis", "volumetric_max")).strip().lower()
    if billing_basis == "actual_weight" or volume_m3 is None:
        return actual

    default_factor = (
        _DEFAULT_DIM_FACTOR_AIR
        if (mode or "").lower() == "air"
        else _DEFAULT_DIM_FACTOR_SEA
    )
    dim_factor = _to_decimal(
        metadata.get("dim_factor_kg_per_m3"), default=default_factor
    )
    volumetric = volume_m3 * dim_factor
    return max(actual, volumetric)


def calculate_shipping_for_routes(
    *,
    routes: list[ShippingRoute],
    total_weight_kg: Decimal,
    declared_value: Decimal,
    currency: str,
    total_volume_m3: Decimal | None = None,
    as_of: datetime | None = None,
    customs_declaration_fees: Sequence[CustomsDeclarationFee] = (),
) -> ShippingCostSummary:
    """Calculate shipping for routes.

    ``total_volume_m3`` is the consolidated shipment volume (sum of product
    volumes). When provided together with ``dim_factor_kg_per_m3`` in
    ``route_metadata``, the billable weight is max(actual, volumetric).
    Omit (or pass None) to fall back to actual weight only.

    ``customs_declaration_fees`` are shipment-level charges owed once per
    customs declaration (F3). They are added to the total as-is — never scaled
    by weight, value or line count — and are reported separately so the order
    snapshot shows what was billed for the declaration rather than for
    transport. Non-positive amounts are dropped.
    """
    normalized_weight_kg = max(total_weight_kg, Decimal("0"))
    normalized_declared_value = max(declared_value, Decimal("0"))
    effective_at = as_of or datetime.now(timezone.utc)
    if effective_at.tzinfo is None:
        effective_at = effective_at.replace(tzinfo=timezone.utc)

    breakdowns: list[RouteShippingCostBreakdown] = []
    eta_values: list[int] = []
    carbon_total = 0.0
    has_carbon_value = False

    for route in routes:
        metadata = _route_metadata_to_dict(route)
        weight_unit = _resolve_weight_unit(metadata)
        pricing_effective = _is_pricing_window_effective(metadata, effective_at)

        fixed_fee = _to_decimal(route.base_price)
        price_per_weight_unit = _to_decimal(route.price_per_kg)
        billable_weight_kg = resolve_billable_weight(
            normalized_weight_kg,
            total_volume_m3,
            metadata=metadata,
            mode=getattr(route, "mode", None),
        )
        billable_weight = _convert_weight_from_kg(billable_weight_kg, weight_unit)
        weight_fee = price_per_weight_unit * billable_weight

        value_rate = (
            _extract_value_rate(metadata) if pricing_effective else Decimal("0")
        )
        value_fee = normalized_declared_value * value_rate

        route_total = fixed_fee + weight_fee + value_fee
        if pricing_effective:
            min_total = _extract_bound(metadata, "min_total")
            max_total = _extract_bound(metadata, "max_total")

            if min_total is not None and route_total < min_total:
                route_total = min_total
            if max_total is not None and route_total > max_total:
                route_total = max_total

        quantized_fixed_fee = quantize_amount(fixed_fee, currency)
        quantized_weight_fee = quantize_amount(weight_fee, currency)
        quantized_value_fee = quantize_amount(value_fee, currency)
        quantized_route_total = quantize_amount(route_total, currency)

        breakdowns.append(
            RouteShippingCostBreakdown(
                route_id=route.id,
                route_name=getattr(route, "name", None),
                fixed_fee=quantized_fixed_fee,
                weight_fee=quantized_weight_fee,
                value_fee=quantized_value_fee,
                total_fee=quantized_route_total,
                weight_unit=weight_unit,
                billable_weight=billable_weight,
                eta_days=route.eta_days,
                carbon_footprint_kg_co2e=route.carbon_footprint_kg_co2e,
                pricing_effective=pricing_effective,
            )
        )

        if route.eta_days is not None:
            eta_values.append(route.eta_days)

        if route.carbon_footprint_kg_co2e is not None:
            has_carbon_value = True
            carbon_total += route.carbon_footprint_kg_co2e

    declaration_fees = tuple(
        CustomsDeclarationFee(
            place_id=fee.place_id,
            place_name=fee.place_name,
            amount=quantize_amount(fee.amount, currency),
        )
        for fee in customs_declaration_fees
        if fee.amount > 0
    )

    total_fee = quantize_amount(
        sum((item.total_fee for item in breakdowns), Decimal("0"))
        + sum((fee.amount for fee in declaration_fees), Decimal("0")),
        currency,
    )

    eta_days: int | None
    if breakdowns and len(eta_values) == len(breakdowns):
        eta_days = sum(eta_values)
    else:
        eta_days = None

    carbon_footprint: float | None = carbon_total if has_carbon_value else None

    return ShippingCostSummary(
        total_fee=total_fee,
        currency=currency,
        breakdown=breakdowns,
        eta_days=eta_days,
        carbon_footprint_kg_co2e=carbon_footprint,
        customs_declaration_fees=declaration_fees,
    )


def serialize_shipping_cost_summary(summary: ShippingCostSummary) -> dict[str, Any]:
    """JSON-safe snapshot of a shipping cost summary (decimals rendered as strings)."""

    return {
        "currency": summary.currency,
        "total_fee": str(summary.total_fee),
        "eta_days": summary.eta_days,
        "carbon_footprint_kg_co2e": summary.carbon_footprint_kg_co2e,
        "customs_declaration_fees": [
            {
                "place_id": str(fee.place_id),
                "place_name": fee.place_name,
                "amount": str(fee.amount),
            }
            for fee in summary.customs_declaration_fees
        ],
        "segments": [
            {
                "route_id": str(segment.route_id),
                "route_name": segment.route_name,
                "fixed_fee": str(segment.fixed_fee),
                "weight_fee": str(segment.weight_fee),
                "value_fee": str(segment.value_fee),
                "total_fee": str(segment.total_fee),
                "weight_unit": segment.weight_unit,
                "billable_weight": str(segment.billable_weight),
                "eta_days": segment.eta_days,
                "carbon_footprint_kg_co2e": segment.carbon_footprint_kg_co2e,
                "pricing_effective": segment.pricing_effective,
            }
            for segment in summary.breakdown
        ],
    }
