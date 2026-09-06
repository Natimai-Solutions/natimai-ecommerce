"""Pure rules of the origin customs regime (no database)."""

from types import SimpleNamespace
from typing import cast

from app.features.place.models import Place
from app.features.shipping.services.origin import (
    OriginRegime,
    parse_country_list,
    resolve_origin_regime,
)


def _place(country: str | None, regime: str | None = None) -> Place:
    return cast(Place, SimpleNamespace(country=country, customs_regime=regime))


_MAIN_PF = _place("PF")


def test_same_country_is_domestic() -> None:
    assert resolve_origin_regime(_place("PF"), _MAIN_PF) is OriginRegime.DOMESTIC
    assert resolve_origin_regime(_place("pf "), _MAIN_PF) is OriginRegime.DOMESTIC


def test_other_country_is_import() -> None:
    assert resolve_origin_regime(_place("FR"), _MAIN_PF) is OriginRegime.IMPORT


def test_customs_free_country_counts_as_domestic() -> None:
    free = parse_country_list("fr, DE")
    assert (
        resolve_origin_regime(_place("FR"), _MAIN_PF, free_countries=free)
        is OriginRegime.DOMESTIC
    )
    assert (
        resolve_origin_regime(_place("US"), _MAIN_PF, free_countries=free)
        is OriginRegime.IMPORT
    )


def test_place_override_wins_over_countries() -> None:
    assert (
        resolve_origin_regime(_place("FR", "domestic"), _MAIN_PF)
        is OriginRegime.DOMESTIC
    )
    assert (
        resolve_origin_regime(_place("PF", "import"), _MAIN_PF) is OriginRegime.IMPORT
    )
    # An override does not even need the main warehouse to be known.
    assert (
        resolve_origin_regime(_place(None, "domestic"), None) is OriginRegime.DOMESTIC
    )


def test_unknown_when_not_configured() -> None:
    assert resolve_origin_regime(None, _MAIN_PF) is OriginRegime.UNKNOWN
    assert resolve_origin_regime(_place(None), _MAIN_PF) is OriginRegime.UNKNOWN
    assert resolve_origin_regime(_place("FR"), None) is OriginRegime.UNKNOWN
    assert resolve_origin_regime(_place("FR"), _place(None)) is OriginRegime.UNKNOWN


def test_unknown_still_applies_customs() -> None:
    # Visible over-pricing beats silent under-pricing.
    assert OriginRegime.UNKNOWN.applies_customs is True
    assert OriginRegime.IMPORT.applies_customs is True
    assert OriginRegime.DOMESTIC.applies_customs is False


def test_parse_country_list() -> None:
    assert parse_country_list(None) == frozenset()
    assert parse_country_list(" , ") == frozenset()
    assert parse_country_list("fr,DE , it") == frozenset({"FR", "DE", "IT"})
