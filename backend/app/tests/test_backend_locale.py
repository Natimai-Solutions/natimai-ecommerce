"""Backend language (R7 / L3): request language, e-mails, error messages."""

from __future__ import annotations

import pathlib
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.core.error_messages import EN, localized_message
from app.core.i18n import (
    format_date,
    format_money,
    from_accept_language,
    normalize_locale,
    reset_request_locale,
    resolve_locale,
    set_request_locale,
)
from app.features.notification.email_renderer import render_email
from app.tests.api.test_email_renderer import _SAMPLE_CONTEXT

_EMAILS = pathlib.Path(__file__).resolve().parents[1] / "templates" / "email"
#: Internal messages, sent to the shop's team: French only.
_INTERNAL = {"admin_payment_event", "quote_request"}


def test_accept_language_parsing() -> None:
    assert from_accept_language("de-DE,de;q=0.9,en;q=0.8,fr;q=0.7") == "en"
    assert from_accept_language("fr-PF") == "fr"
    assert from_accept_language("es") is None
    assert normalize_locale("EN_gb") == "en"
    assert resolve_locale(None, "xx", "en") == "en"


def test_every_customer_email_has_an_english_version() -> None:
    names = {p.name.split(".")[0] for p in (_EMAILS / "fr").iterdir()}
    for name in sorted(names - _INTERNAL):
        for suffix in ("subject.txt", "txt", "html"):
            assert (_EMAILS / "en" / f"{name}.{suffix}").is_file(), (name, suffix)


@pytest.mark.parametrize("name", sorted(set(_SAMPLE_CONTEXT) - _INTERNAL))
def test_english_emails_render_in_english(name: str) -> None:
    email = render_email(name, lang="en", **_SAMPLE_CONTEXT[name])
    assert email.subject and email.text and email.html
    assert 'lang="en"' in email.html
    assert "Bonjour" not in email.text
    assert "please do not reply" in email.html


def test_email_language_follows_the_request_by_default() -> None:
    token = set_request_locale("en")
    try:
        email = render_email("order_created", **_SAMPLE_CONTEXT["order_created"])
    finally:
        reset_request_locale(token)
    assert email.subject.startswith("Your order")
    assert render_email(
        "order_created", **_SAMPLE_CONTEXT["order_created"]
    ).subject.startswith("Votre commande")


def test_money_and_dates_follow_the_language() -> None:
    assert format_money("12500", "XPF", "en") == "12,500 XPF"
    assert format_money("12500", "XPF", "fr") == "12 500 XPF"
    assert format_money("19.9", "EUR", "fr") == "19,90 EUR"
    assert format_date(date(2026, 6, 23), "en") == "23 Jun 2026"
    assert format_date("2026-06-23T10:00:00Z", "fr") == "23/06/2026"


def test_error_messages_follow_accept_language() -> None:
    assert localized_message("cart.cgv.not_accepted", "Les CGV…", "fr") == "Les CGV…"
    assert (
        localized_message("cart.cgv.not_accepted", "Les CGV…", "en")
        == EN["cart.cgv.not_accepted"]
    )
    assert localized_message("not.listed", "Message", "en") == "Message"

    from app.main import app

    with TestClient(app) as client:
        form = {"username": "nobody@example.com", "password": "wrong-password"}
        en = client.post(
            "/api/v1/login/access-token", data=form, headers={"Accept-Language": "en"}
        )
        fr = client.post(
            "/api/v1/login/access-token", data=form, headers={"Accept-Language": "fr"}
        )
    assert en.json()["error"]["code"] == fr.json()["error"]["code"]
    assert en.json()["error"]["message"] == "Incorrect e-mail or password."
    assert fr.json()["error"]["message"] != en.json()["error"]["message"]
