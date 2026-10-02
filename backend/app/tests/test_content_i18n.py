"""Translated content (R9 / T3): validation, staleness and overlay."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core import i18n
from app.core.content_i18n import (
    PRODUCT_FIELDS,
    InvalidTranslations,
    clean_translations,
    localize,
    source_digest,
    translation_status,
)

SOURCE = {"name": "Souris", "description": "Sans fil", "long_description": None}


def test_clean_drops_blank_fields_unknown_fields_and_the_default_language() -> None:
    cleaned = clean_translations(
        {
            "en": {"name": " Mouse ", "description": "", "price": "12", "x": 1},
            "fr": {"name": "ignoré"},
            "EN-GB": {"long_description": "<p>Wireless</p>"},
        },
        previous=None,
        source_values=SOURCE,
        fields=PRODUCT_FIELDS,
    )
    # en-GB normalises to en and the two entries merge on the last one seen.
    assert set(cleaned) == {"en"}
    assert cleaned["en"]["long_description"] == "<p>Wireless</p>"
    assert "price" not in cleaned["en"]
    assert cleaned["en"]["_source"] == source_digest(SOURCE, PRODUCT_FIELDS)

    assert (
        clean_translations(
            {"en": {"name": "  "}},
            previous=None,
            source_values=SOURCE,
            fields=PRODUCT_FIELDS,
        )
        == {}
    )
    with pytest.raises(InvalidTranslations):
        clean_translations(
            {"es": {"name": "Ratón"}},
            previous=None,
            source_values=SOURCE,
            fields=PRODUCT_FIELDS,
        )


def test_a_translation_goes_stale_when_the_source_changes_until_reviewed() -> None:
    first = clean_translations(
        {"en": {"name": "Mouse"}},
        previous=None,
        source_values=SOURCE,
        fields=PRODUCT_FIELDS,
    )
    assert translation_status(first, SOURCE, PRODUCT_FIELDS, locales=["fr", "en"]) == {
        "en": "ok"
    }

    edited = {**SOURCE, "name": "Souris ergonomique"}
    assert translation_status(first, edited, PRODUCT_FIELDS, locales=["en"]) == {
        "en": "stale"
    }

    # Saving the form again with the same English text keeps the old digest…
    resent = clean_translations(
        first, previous=first, source_values=edited, fields=PRODUCT_FIELDS
    )
    assert resent["en"]["_source"] == first["en"]["_source"]
    assert translation_status(resent, edited, PRODUCT_FIELDS, locales=["en"]) == {
        "en": "stale"
    }
    # …a changed text, or an explicit review, refreshes it.
    retranslated = clean_translations(
        {"en": {"name": "Ergonomic mouse"}},
        previous=first,
        source_values=edited,
        fields=PRODUCT_FIELDS,
    )
    assert translation_status(retranslated, edited, PRODUCT_FIELDS, locales=["en"]) == {
        "en": "ok"
    }
    reviewed = clean_translations(
        {"en": {"name": "Mouse", "_refresh": True}},
        previous=first,
        source_values=edited,
        fields=PRODUCT_FIELDS,
    )
    assert translation_status(reviewed, edited, PRODUCT_FIELDS, locales=["en"]) == {
        "en": "ok"
    }
    assert translation_status({}, edited, PRODUCT_FIELDS, locales=["en"]) == {
        "en": "missing"
    }


def test_localize_overlays_the_request_language_and_keeps_the_source_elsewhere() -> (
    None
):
    public = SimpleNamespace(
        name="Souris",
        description="Sans fil",
        long_description=None,
        translations={"en": {"name": "Mouse", "_source": "x"}},
    )
    localize(public, PRODUCT_FIELDS, lang="en")
    assert (public.name, public.description) == ("Mouse", "Sans fil")

    token = i18n.set_request_locale("fr")
    try:
        again = SimpleNamespace(name="Souris", translations={"en": {"name": "Mouse"}})
        localize(again, PRODUCT_FIELDS)
        assert again.name == "Souris"
    finally:
        i18n.reset_request_locale(token)
