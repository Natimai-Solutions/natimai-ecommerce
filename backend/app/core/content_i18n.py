"""Translated content (R9 / T3): one JSONB column per translatable entity.

Products, categories, pages, homepage blocks and spec definitions keep their
columns in the shop's default language (what the supplier sync and Icecat
write) and carry a ``translations`` column of the form::

    {"en": {"name": "...", "long_description": "...", "_source": "9f2c…"}}

``_source`` is a digest of the default-language texts at the time the
translation was saved (Shopify keeps the same kind of fingerprint): when the
source text changes afterwards, the translation reads as *stale* in the
back-office until someone looks at it again.

The public API resolves the language of the request (``Accept-Language``,
see :mod:`app.core.i18n`) and overlays the translation on the public schema,
field by field, falling back to the default language for anything missing.
The back-office always reads and writes the source language plus the raw
``translations`` mapping.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from app.core.i18n import (
    SUPPORTED_LOCALES,
    default_locale,
    normalize_locale,
    offered_locales,
    request_locale,
)

Translations = dict[str, dict[str, Any]]

#: Metadata key inside a language entry: digest of the source texts.
SOURCE_KEY = "_source"
#: Sent by the back-office to mark a translation as reviewed (fresh digest)
#: without changing its text.
REFRESH_KEY = "_refresh"

#: Translatable fields per entity (the column names of the default language).
PRODUCT_FIELDS: tuple[str, ...] = ("name", "description", "long_description")
CATEGORY_FIELDS: tuple[str, ...] = ("display_name", "description")
CONTENT_PAGE_FIELDS: tuple[str, ...] = ("title", "body_html")
HOMEPAGE_BLOCK_FIELDS: tuple[str, ...] = ("title", "subtitle", "cta_label", "alt")
#: ``label_fr`` is the column of the default-language label (historical name).
SPEC_DEFINITION_FIELDS: tuple[str, ...] = ("label_fr",)


class InvalidTranslations(ValueError):
    """The back-office sent a language the shop does not know."""


def source_digest(values: Mapping[str, Any], fields: Sequence[str]) -> str:
    """Fingerprint of the default-language texts (order of ``fields``)."""
    joined = "\x1f".join(str(values.get(field) or "").strip() for field in fields)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:16]  # noqa: S324


def _texts(entry: Mapping[str, Any], fields: Sequence[str]) -> dict[str, str]:
    """The non-blank translated texts of one language entry."""
    out: dict[str, str] = {}
    for field in fields:
        value = entry.get(field)
        if isinstance(value, str) and value.strip():
            out[field] = value.strip()
    return out


def clean_translations(
    incoming: Mapping[str, Any] | None,
    *,
    previous: Mapping[str, Any] | None,
    source_values: Mapping[str, Any],
    fields: Sequence[str],
) -> Translations:
    """Validate and stamp what the back-office sent.

    * a language outside :data:`SUPPORTED_LOCALES` is refused
      (:class:`InvalidTranslations`); the default language is ignored (its
      texts live in the columns);
    * unknown fields and blank texts are dropped; a language without any text
      disappears;
    * ``_source`` is kept from ``previous`` when the texts did not change, so
      a save that only touched the source language still shows the
      translation as stale; it is refreshed when the texts changed or when
      the entry carries ``_refresh``.
    """
    if not incoming:
        return {}
    previous = previous or {}
    default = default_locale()
    digest = source_digest(source_values, fields)
    out: Translations = {}
    for raw_lang, entry in incoming.items():
        lang = normalize_locale(raw_lang)
        if lang is None:
            raise InvalidTranslations(
                f"langue inconnue : {raw_lang!r} (attendu : "
                f"{', '.join(SUPPORTED_LOCALES)})"
            )
        if lang == default or not isinstance(entry, Mapping):
            continue
        texts = _texts(entry, fields)
        if not texts:
            continue
        before = previous.get(lang) or {}
        unchanged = _texts(before, fields) == texts and SOURCE_KEY in before
        refresh = bool(entry.get(REFRESH_KEY)) or not unchanged
        out[lang] = {**texts, SOURCE_KEY: digest if refresh else before[SOURCE_KEY]}
    return out


def translation_status(
    translations: Mapping[str, Any] | None,
    source_values: Mapping[str, Any],
    fields: Sequence[str],
    *,
    locales: Iterable[str] | None = None,
) -> dict[str, str]:
    """``{"en": "ok" | "stale" | "missing"}`` for every offered language
    other than the default (what the back-office shows next to the tabs)."""
    translations = translations or {}
    default = default_locale()
    digest = source_digest(source_values, fields)
    status: dict[str, str] = {}
    for lang in locales if locales is not None else offered_locales():
        if lang == default:
            continue
        entry = translations.get(lang) or {}
        if not _texts(entry, fields):
            status[lang] = "missing"
        elif entry.get(SOURCE_KEY) != digest:
            status[lang] = "stale"
        else:
            status[lang] = "ok"
    return status


def translated_values(
    translations: Mapping[str, Any] | None, fields: Sequence[str], lang: str
) -> dict[str, str]:
    """The texts of ``lang`` (non-blank only), empty for the default language."""
    if not translations or lang == default_locale():
        return {}
    return _texts(translations.get(lang) or {}, fields)


def localize(obj: Any, fields: Sequence[str], *, lang: str | None = None) -> Any:
    """Overlay the translation of ``lang`` (default: the request's language)
    on a public schema instance, field by field; the source text stays for a
    field without translation. Returns ``obj``."""
    code = lang or request_locale()
    for field, value in translated_values(
        getattr(obj, "translations", None), fields, code
    ).items():
        setattr(obj, field, value)
    return obj


def localize_all(items: Iterable[Any], fields: Sequence[str]) -> None:
    """:func:`localize` every item for the request's language (one lookup)."""
    code = request_locale()
    if code == default_locale():
        return
    for item in items:
        localize(item, fields, lang=code)


__all__ = [
    "CATEGORY_FIELDS",
    "CONTENT_PAGE_FIELDS",
    "HOMEPAGE_BLOCK_FIELDS",
    "PRODUCT_FIELDS",
    "REFRESH_KEY",
    "SOURCE_KEY",
    "SPEC_DEFINITION_FIELDS",
    "InvalidTranslations",
    "Translations",
    "clean_translations",
    "localize",
    "localize_all",
    "source_digest",
    "translated_values",
    "translation_status",
]
