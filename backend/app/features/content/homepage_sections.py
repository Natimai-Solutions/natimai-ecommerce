"""Homepage sections: their settings, their audience, and who sees them.

A section of the homepage is a ``homepage_blocks`` row. Its ``config``
depends on its kind (how many products, over how many days…) and its
``audience`` says who it is shown to (chantier accueil et messagerie, R1 and
R8): everyone, visitors only, or signed-in customers — optionally of some
price groups only — and optionally in some languages only.

The storefront renders the visitor's page on the server (always anonymous);
a signed-in customer's page is asked again from the browser.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.i18n import normalize_locale, offered_locales


class InvalidSection(ValueError):
    """``config`` or ``audience`` does not fit the section type."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _NoConfig(_Strict):
    pass


class _CategoriesConfig(_Strict):
    limit: int = Field(default=8, ge=2, le=24)


class _FeaturedConfig(_Strict):
    limit: int = Field(default=8, ge=2, le=24)


class _PopularConfig(_Strict):
    limit: int = Field(default=8, ge=2, le=24)
    days: int = Field(default=30, ge=1, le=365)


_CONFIGS: dict[str, type[_Strict]] = {
    "hero": _NoConfig,
    "banner": _NoConfig,
    "categories": _CategoriesConfig,
    "featured": _FeaturedConfig,
    "popular": _PopularConfig,
}


class Audience(_Strict):
    """Who a section is shown to."""

    scope: Literal["all", "guest", "customer"] = "all"
    #: Customers of these price groups only (``customer`` scope); empty = all.
    price_group_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    #: Visitors browsing in these languages only; empty = every language.
    locales: list[str] = Field(default_factory=list, max_length=10)


def clean_config(kind: str, raw: dict[str, Any] | None) -> dict[str, Any]:
    """The section's settings, complete (defaults filled) and checked."""
    model = _CONFIGS.get(kind)
    if model is None:
        raise InvalidSection(f"unknown kind {kind}")
    try:
        return model.model_validate(raw or {}).model_dump(mode="json")
    except ValidationError as exc:
        raise InvalidSection(str(exc)) from exc


def clean_audience(raw: dict[str, Any] | None) -> dict[str, Any]:
    """The audience, checked: groups only for customers, offered languages."""
    try:
        audience = Audience.model_validate(raw or {})
    except ValidationError as exc:
        raise InvalidSection(str(exc)) from exc
    if audience.price_group_ids and audience.scope != "customer":
        raise InvalidSection("price groups are for the customer scope only")
    offered = set(offered_locales())
    locales: list[str] = []
    for code in audience.locales:
        normalized = normalize_locale(code)
        if not normalized or normalized not in offered:
            raise InvalidSection(f"language not offered: {code}")
        if normalized not in locales:
            locales.append(normalized)
    audience.locales = locales
    audience.price_group_ids = list(dict.fromkeys(audience.price_group_ids))
    return audience.model_dump(mode="json")


def audience_of(raw: dict[str, Any] | None) -> Audience:
    """A stored audience (already cleaned), tolerant of an older empty value."""
    try:
        return Audience.model_validate(raw or {})
    except ValidationError:
        # A row edited by hand: shown to nobody rather than to everybody.
        return Audience(scope="customer", price_group_ids=[uuid.UUID(int=0)])


@dataclass(frozen=True)
class Viewer:
    """Who is looking at the homepage."""

    signed_in: bool
    price_group_id: uuid.UUID | None
    locale: str


def is_shown_to(raw: dict[str, Any] | None, viewer: Viewer) -> bool:
    """Whether a section with this audience is shown to ``viewer``."""
    audience = audience_of(raw)
    if audience.locales and viewer.locale not in audience.locales:
        return False
    if audience.scope == "guest":
        return not viewer.signed_in
    if audience.scope == "customer":
        if not viewer.signed_in:
            return False
        if audience.price_group_ids:
            return viewer.price_group_id in audience.price_group_ids
    return True


def audiences_overlap(a: dict[str, Any] | None, b: dict[str, Any] | None) -> bool:
    """Whether some viewer could be shown both sections (two heroes on the
    same page: only one would ever appear)."""
    first, second = audience_of(a), audience_of(b)
    if (
        first.locales
        and second.locales
        and not set(first.locales) & set(second.locales)
    ):
        return False
    scopes = {first.scope, second.scope}
    if scopes == {"guest", "customer"}:
        return False
    if (
        first.scope == "customer"
        and second.scope == "customer"
        and first.price_group_ids
        and second.price_group_ids
        and not set(first.price_group_ids) & set(second.price_group_ids)
    ):
        return False
    return True


__all__ = [
    "Audience",
    "InvalidSection",
    "Viewer",
    "audience_of",
    "audiences_overlap",
    "clean_audience",
    "clean_config",
    "is_shown_to",
]
