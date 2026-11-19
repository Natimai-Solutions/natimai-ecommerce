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
    #: ``auto``: first-level categories, those with an image first;
    #: ``manual``: the categories listed in the section, in order.
    mode: Literal["auto", "manual"] = "auto"


#: How a product section is laid out: a grid, or one scrolling row.
Layout = Literal["grid", "carousel"]


class _CollectionConfig(_Strict):
    source: Literal[
        "manual",
        "category",
        "brand",
        "newest",
        "promotion",
        "popular",
        "best_sellers",
    ] = "manual"
    category_id: uuid.UUID | None = None
    #: ``brand`` source (lot BR): the products of this brand sheet.
    brand_id: uuid.UUID | None = None
    layout: Layout = "grid"
    limit: int = Field(default=8, ge=2, le=24)
    days: int = Field(default=30, ge=1, le=365)
    sort: Literal["newest", "price_asc", "price_desc", "name"] = "newest"


class _FeaturedConfig(_Strict):
    limit: int = Field(default=8, ge=2, le=24)
    layout: Layout = "grid"


class _PopularConfig(_Strict):
    limit: int = Field(default=8, ge=2, le=24)
    days: int = Field(default=30, ge=1, le=365)
    layout: Layout = "grid"


#: Pictograms of a reassurance band: a closed list, drawn by the storefront
#: (no icon address typed in the admin, lot A3 / R5).
REASSURANCE_ICONS: tuple[str, ...] = (
    "truck",
    "boat",
    "map_pin",
    "package",
    "lock",
    "shield",
    "credit_card",
    "seal",
    "chat",
    "phone",
    "clock",
    "returns",
    "tag",
    "star",
)


class _ReassuranceItem(_Strict):
    icon: Literal[REASSURANCE_ICONS]  # type: ignore[valid-type]
    text: str = Field(min_length=1, max_length=80)
    link: str | None = Field(default=None, max_length=500)
    #: The text in the other languages: ``{"en": "…"}``.
    translations: dict[str, str] = Field(default_factory=dict, max_length=10)


class _ReassuranceConfig(_Strict):
    items: list[_ReassuranceItem] = Field(min_length=2, max_length=4)


class _BrandStripConfig(_Strict):
    #: ``auto``: the validated brands with a logo, best-stocked first;
    #: ``manual``: the brands listed in the section, in order.
    mode: Literal["auto", "manual"] = "auto"
    limit: int = Field(default=12, ge=3, le=24)


class _RichTextConfig(_Strict):
    #: Side of the optional image.
    image_side: Literal["left", "right"] = "right"


class _PersonalConfig(_Strict):
    #: ``recently_viewed`` is kept in the browser (visitors too); the others
    #: are a signed-in customer's own (lot A5 / R9).
    source: Literal["recently_viewed", "reorder", "wishlist", "current_order"] = (
        "recently_viewed"
    )
    limit: int = Field(default=8, ge=2, le=12)


#: Personal sections a visitor never gets (they need an account).
ACCOUNT_SOURCES: frozenset[str] = frozenset({"reorder", "wishlist", "current_order"})


_CONFIGS: dict[str, type[_Strict]] = {
    "personal": _PersonalConfig,
    "hero": _NoConfig,
    "banner": _NoConfig,
    "announcement": _NoConfig,
    "reassurance": _ReassuranceConfig,
    "brand_strip": _BrandStripConfig,
    "rich_text": _RichTextConfig,
    "categories": _CategoriesConfig,
    "featured": _FeaturedConfig,
    "popular": _PopularConfig,
    "collection": _CollectionConfig,
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
        config = model.model_validate(raw or {})
    except ValidationError as exc:
        raise InvalidSection(str(exc)) from exc
    if isinstance(config, _CollectionConfig) and (
        (config.source == "category") != (config.category_id is not None)
    ):
        raise InvalidSection("a category is required for, and only for, that source")
    if isinstance(config, _CollectionConfig) and (
        (config.source == "brand") != (config.brand_id is not None)
    ):
        raise InvalidSection("a brand is required for, and only for, that source")
    if isinstance(config, _ReassuranceConfig):
        offered = set(offered_locales())
        for item in config.items:
            item.text = item.text.strip()
            item.link = (item.link or "").strip() or None
            if item.link and not is_safe_link(item.link):
                raise InvalidSection("unsafe link")
            texts: dict[str, str] = {}
            for code, text in item.translations.items():
                lang = normalize_locale(code)
                if not lang or lang not in offered:
                    raise InvalidSection(f"language not offered: {code}")
                if text.strip():
                    texts[lang] = text.strip()[:80]
            item.translations = texts
    return config.model_dump(mode="json")


def stored_config(kind: str, raw: dict[str, Any] | None) -> dict[str, Any] | None:
    """A stored section's settings, read back for display: never raises.

    ``clean_config`` checks what the admin writes; a stored value can stop
    passing it later without anyone editing the section — a language
    removed from the offered ones, a setting dropped by a rollback. The
    page must not fall over for that (a 500 on the homepage, the admin
    screen unable to load): the obsolete parts are ignored and, if the rest
    is still unusable, ``None`` says to leave the section out.
    """
    try:
        return clean_config(kind, raw)
    except InvalidSection:
        pass
    model = _CONFIGS.get(kind)
    if model is None:
        return None
    data = {k: v for k, v in (raw or {}).items() if k in model.model_fields}
    if kind == "reassurance":
        offered = set(offered_locales())
        data["items"] = [
            {
                **item,
                "translations": {
                    code: text
                    for code, text in (item.get("translations") or {}).items()
                    if normalize_locale(code) in offered
                },
            }
            for item in data.get("items") or []
            if isinstance(item, dict)
        ]
    try:
        return clean_config(kind, data)
    except InvalidSection:
        return None


def is_safe_link(link: str) -> bool:
    """A storefront path or an https address: never ``javascript:``, a
    protocol-relative URL (``//`` or ``/\\``) nor a control character."""
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in link):
        return False
    if link.startswith("/"):
        return not link.startswith("//") and not link.startswith("/\\")
    return link.startswith("https://")


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
    "ACCOUNT_SOURCES",
    "REASSURANCE_ICONS",
    "is_safe_link",
    "Audience",
    "InvalidSection",
    "Viewer",
    "audience_of",
    "audiences_overlap",
    "clean_audience",
    "clean_config",
    "stored_config",
    "is_shown_to",
]
