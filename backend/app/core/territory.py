"""Territory profiles: what a deployment assumes about where it sells.

The platform was built for French Polynesia (XPF, TGC, Papeete customs,
island geography). Nothing in the code should hard-code that: a profile
gathers the currency, the tax territory and its rates, the country and the
starter data, and ``TERRITORY_PROFILE`` picks one. Every individual value
can still be overridden by its own environment variable.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class TaxRateSpec:
    """One seeded tax rate of a territory."""

    code: str
    label: str
    rate_pct: Decimal


@dataclass(frozen=True)
class TerritoryProfile:
    """Everything a territory decides for a deployment."""

    code: str
    label: str
    #: ISO country code of the shop (address fallback, place tree root).
    country_code: str
    #: Reference (billing) currency.
    currency: str
    #: ``TaxRate.territory_code`` of the shop's own rates.
    tax_territory_code: str
    #: Rate applied when neither the product nor its category says otherwise.
    default_tax_code: str
    tax_rates: tuple[TaxRateSpec, ...]
    #: Starter FX rates: 1 unit of ``code`` = ``rate`` units of the reference.
    currency_rates: tuple[tuple[str, Decimal], ...]
    #: Whether the French Polynesia import corridor / island tree is seeded.
    seed_french_polynesia_logistics: bool
    #: Wording of the legal identity screen.
    registration_label: str
    registry_label: str


PF = TerritoryProfile(
    code="PF",
    label="Polynésie française",
    country_code="PF",
    currency="XPF",
    tax_territory_code="PF",
    default_tax_code="TGC_NORMAL",
    tax_rates=(
        TaxRateSpec("TGC_NORMAL", "TGC normal", Decimal("16.00")),
        TaxRateSpec("TGC_REDUIT", "TGC reduit", Decimal("5.00")),
        TaxRateSpec("TGC_EXONERE", "TGC exonere", Decimal("0.00")),
    ),
    currency_rates=(("EUR", Decimal("119.332")), ("USD", Decimal("100.000"))),
    seed_french_polynesia_logistics=True,
    registration_label="Numéro TAHITI (équivalent local du SIRET)",
    registry_label="Numéro au Registre du commerce de Papeete",
)

FR = TerritoryProfile(
    code="FR",
    label="France métropolitaine",
    country_code="FR",
    currency="EUR",
    tax_territory_code="FR",
    default_tax_code="TVA_NORMALE",
    tax_rates=(
        TaxRateSpec("TVA_NORMALE", "TVA taux normal", Decimal("20.00")),
        TaxRateSpec("TVA_INTERMEDIAIRE", "TVA taux intermédiaire", Decimal("10.00")),
        TaxRateSpec("TVA_REDUITE", "TVA taux réduit", Decimal("5.50")),
        TaxRateSpec("TVA_SUPER_REDUITE", "TVA taux particulier", Decimal("2.10")),
        TaxRateSpec("TVA_EXONEREE", "Exonéré de TVA", Decimal("0.00")),
    ),
    currency_rates=(("USD", Decimal("0.920")), ("XPF", Decimal("0.00838"))),
    seed_french_polynesia_logistics=False,
    registration_label="Numéro SIRET",
    registry_label="Numéro RCS (registre du commerce et des sociétés)",
)

TERRITORY_PROFILES: dict[str, TerritoryProfile] = {PF.code: PF, FR.code: FR}


def get_profile(code: str) -> TerritoryProfile:
    """The profile for ``code`` (validated upstream by the settings Literal)."""
    return TERRITORY_PROFILES[code]
