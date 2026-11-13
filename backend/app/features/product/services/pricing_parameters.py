"""Pricing parameters the owner edits in the back-office (``system_settings``).

The price formula (``pricing.py``) reads its referentials from tables — tax
rates, currency rates, categories, price groups. A few knobs are single
numbers with no table of their own; they live in ``system_settings`` so they
are editable without a deployment, and a change re-prices the catalogue.

* ``pricing_payment_commission_pct`` — the card / PSP commission, taken as a
  percentage of what the customer pays. Integrated *in* the price rather
  than added as a fee at checkout: ``price = price_before / (1 − c)``, so
  the shop nets ``price_before`` after the commission. Applies to the
  domestic and import modes (a fixed price is what the admin typed).
* ``pricing_fx_safety_margin_pct`` — a cushion on costs quoted in a foreign
  currency: the converted cost is raised by this percentage before the
  formula runs, so a rate that moves between the sale and the supplier
  invoice does not eat the margin. A cost already in the reference
  currency carries no exchange risk and is left alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from sqlmodel.ext.asyncio.session import AsyncSession

from app.utils.money import reference_price


@dataclass(frozen=True)
class PricingParameterSpec:
    """One numeric setting: its key, admin help text, default and bounds."""

    key: str
    description: str
    default: Decimal
    minimum: Decimal
    #: Exclusive upper bound (a 100 % commission would divide by zero).
    below: Decimal


PAYMENT_COMMISSION_KEY = "pricing_payment_commission_pct"
FX_SAFETY_MARGIN_KEY = "pricing_fx_safety_margin_pct"
INSURANCE_RATE_KEY = "insurance_rate_pct"

PRICING_SETTINGS: tuple[PricingParameterSpec, ...] = (
    PricingParameterSpec(
        PAYMENT_COMMISSION_KEY,
        "Commission de paiement (CB / prestataire) en % du prix payé, intégrée "
        "dans le prix de vente : prix = prix hors commission ÷ (1 − c). "
        "0 = aucune. Modifier cette valeur recalcule tous les prix.",
        default=Decimal("0"),
        minimum=Decimal("0"),
        below=Decimal("100"),
    ),
    PricingParameterSpec(
        FX_SAFETY_MARGIN_KEY,
        "Marge de sécurité sur le change en % : les coûts fournisseur en devise "
        "étrangère (USD, EUR…) sont majorés de ce pourcentage après conversion, "
        "avant le calcul du prix. 0 = aucune. Modifier cette valeur recalcule "
        "tous les prix.",
        default=Decimal("0"),
        minimum=Decimal("0"),
        below=Decimal("100"),
    ),
)

PRICING_SETTING_KEYS: frozenset[str] = frozenset(s.key for s in PRICING_SETTINGS)
_SPEC_BY_KEY = {s.key: s for s in PRICING_SETTINGS}


def parse_pricing_value(key: str, raw: str) -> Decimal:
    """The number behind a pricing setting; ``ValueError`` when unusable."""
    spec = _SPEC_BY_KEY[key]
    text = (raw or "").strip().replace(",", ".").replace("%", "").strip()
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{key}: « {raw} » n'est pas un nombre") from exc
    if not value.is_finite() or value < spec.minimum or value >= spec.below:
        raise ValueError(
            f"{key}: la valeur doit être comprise entre {spec.minimum} et "
            f"{spec.below} (exclu), reçu {value}"
        )
    return value


@dataclass(frozen=True)
class PricingParameters:
    """The knobs the formula reads, already parsed (defaults when unset)."""

    payment_commission_pct: Decimal = Decimal("0")
    fx_safety_margin_pct: Decimal = Decimal("0")
    #: Transport insurance, % of the goods + freight (runtime setting
    #: ``insurance_rate_pct``, fallback ``INSURANCE_RATE_PCT``).
    insurance_rate_pct: Decimal = Decimal("0")


async def load_pricing_parameters(session: AsyncSession) -> PricingParameters:
    """Read the pricing settings (runtime registry); an absent or unparsable
    row is its default."""
    from app.core import runtime_settings

    values = await runtime_settings.get_many(
        [*PRICING_SETTING_KEYS, INSURANCE_RATE_KEY], session
    )
    return PricingParameters(
        insurance_rate_pct=Decimal(str(values[INSURANCE_RATE_KEY] or 0)),
        payment_commission_pct=values[PAYMENT_COMMISSION_KEY],
        fx_safety_margin_pct=values[FX_SAFETY_MARGIN_KEY],
    )


def apply_fx_safety_margin(
    cost_in_reference: Decimal, margin_pct: Decimal, *, converted: bool
) -> Decimal:
    """Raise a converted cost by the safety margin; untouched when the cost
    was already in the reference currency (no exchange risk)."""
    if not converted or margin_pct <= 0:
        return cost_in_reference
    raised = cost_in_reference * (Decimal("1") + margin_pct / Decimal("100"))
    return raised.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def apply_payment_commission(price: Decimal, commission_pct: Decimal) -> Decimal:
    """Gross the price up so that ``price`` is what remains after the
    commission. The last step of the sale price: the result is rounded to the
    reference currency's unit (whole francs in XPF — audit 2026-11)."""
    if commission_pct <= 0:
        return reference_price(price)
    grossed = price / (Decimal("1") - commission_pct / Decimal("100"))
    return reference_price(grossed)


__all__ = [
    "FX_SAFETY_MARGIN_KEY",
    "PAYMENT_COMMISSION_KEY",
    "PRICING_SETTINGS",
    "PRICING_SETTING_KEYS",
    "PricingParameterSpec",
    "PricingParameters",
    "apply_fx_safety_margin",
    "apply_payment_commission",
    "load_pricing_parameters",
    "parse_pricing_value",
]
