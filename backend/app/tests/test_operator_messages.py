"""Messages to the operator: both languages, the same values, the language
chosen by ``operator_locale`` (decision of 18/11/2026)."""

from __future__ import annotations

import re

import pytest

from app.core import operator_messages as om

PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")


def test_every_message_has_both_languages_with_the_same_values() -> None:
    for key, (en, fr) in om.MESSAGES.items():
        assert en and fr, key
        assert set(PLACEHOLDER.findall(en)) == set(PLACEHOLDER.findall(fr)), key


def test_the_operator_language_is_chosen(monkeypatch: pytest.MonkeyPatch) -> None:
    values = {"operator_locale": "en", "shop_default_locale": "fr"}
    monkeypatch.setattr("app.core.runtime_settings.peek", lambda key: values.get(key))

    assert om.operator_text("outbox.stuck", minutes=12).startswith("Event queue stuck")
    values["operator_locale"] = ""
    assert om.operator_text("outbox.stuck", minutes=12).startswith(
        "File d'événements bloquée"
    )
    assert om.operator_text("outbox.stuck", locale="en", minutes=1).startswith("Event")


def test_a_missing_value_or_key_never_breaks_an_alert() -> None:
    assert om.operator_text("no.such.key") == "no.such.key"
    assert "{minutes}" in om.operator_text("outbox.stuck", locale="en")
