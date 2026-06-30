"""Tests for the file-based transactional email renderer."""

from __future__ import annotations

from typing import Any

import pytest

from app.features.notification.email_renderer import (
    DEFAULT_LANG,
    render_email,
)

_SAMPLE_CONTEXT: dict[str, dict[str, Any]] = {
    "order_created": {
        "full_name": "Alice",
        "order_id": "ORD-1",
        "total_amount": "1000",
        "currency": "XPF",
        "item_count": 2,
        "shop_name": "Natimai",
    },
    "payment_captured": {
        "full_name": "Alice",
        "order_id": "ORD-1",
        "total_amount": "1000",
        "currency": "XPF",
        "shop_name": "Natimai",
    },
    "payment_rejected": {
        "full_name": "Alice",
        "order_id": "ORD-1",
        "reason": "Carte refusée",
        "shop_name": "Natimai",
    },
    "payment_refunded": {
        "full_name": "Alice",
        "order_id": "ORD-1",
        "amount": "500",
        "currency": "XPF",
        "reason": "Article défectueux",
        "fully_refunded": False,
        "shop_name": "Natimai",
    },
    "shipping_shipped": {
        "full_name": "Alice",
        "order_id": "ORD-1",
        "tracking_ref": "TRK-9",
        "estimated_delivery": "2026-07-01",
        "shop_name": "Natimai",
    },
    "shipping_delivered": {
        "full_name": "Alice",
        "order_id": "ORD-1",
        "shop_name": "Natimai",
    },
    "shipping_progress": {
        "full_name": "Alice",
        "order_id": "ORD-1",
        "tracking_ref": "TRK-9",
        "shop_name": "Natimai",
    },
    "signup_otp": {
        "code": "123456",
        "valid_minutes": 10,
        "shop_name": "Natimai",
    },
    "admin_payment_event": {
        "event_type": "payment.captured",
        "event_label": "Paiement validé",
        "payment_id": "pay_1",
        "order_id": "ord_1",
        "provider_code": "payzen",
        "amount": "1000",
        "currency": "XPF",
        "reference": "ref-9",
        "reason": "",
        "shop_name": "Natimai",
    },
    "quote_request": {
        "subtitle": "Demande transmise depuis le panier public.",
        "contact": "client@example.com",
        "item_count": 1,
        "summary": [{"label": "Email", "value": "client@example.com"}],
        "items": [
            {
                "product_name": "Laptop Test",
                "quantity": "2",
                "unit_price": "1000.00",
                "line_total": "2000.00",
                "image_url": "https://cdn.example.com/laptop.png",
            }
        ],
        "currency": "XPF",
        "subtotal": "2000.00",
        "shop_name": "Natimai",
    },
}


@pytest.mark.parametrize("name", sorted(_SAMPLE_CONTEXT))
def test_every_template_renders_all_parts(name: str) -> None:
    email = render_email(name, **_SAMPLE_CONTEXT[name])
    assert email.subject.strip()
    assert email.text.strip()
    assert "<html" in email.html.lower()
    # subject is a single trimmed line
    assert "\n" not in email.subject


def test_context_values_are_interpolated() -> None:
    email = render_email("order_created", **_SAMPLE_CONTEXT["order_created"])
    assert "ORD-1" in email.subject
    assert "Alice" in email.text
    assert "ORD-1" in email.html
    assert "1000 XPF" in email.text


def test_html_autoescapes_but_text_does_not() -> None:
    ctx = {**_SAMPLE_CONTEXT["payment_rejected"], "reason": "<script>x</script>"}
    email = render_email("payment_rejected", **ctx)
    # HTML body escapes the injected markup (XSS-safe)…
    assert "<script>" not in email.html
    assert "&lt;script&gt;" in email.html
    # …while the plain-text body keeps it verbatim.
    assert "<script>x</script>" in email.text


def test_refund_scope_switches_on_fully_refunded() -> None:
    partial = render_email(
        "payment_refunded", **{**_SAMPLE_CONTEXT["payment_refunded"]}
    )
    assert "partiel" in partial.text.lower()
    assert "partiel" in partial.html.lower()

    full = render_email(
        "payment_refunded",
        **{**_SAMPLE_CONTEXT["payment_refunded"], "fully_refunded": True},
    )
    assert "total" in full.text.lower()
    assert "total" in full.html.lower()


def test_optional_reason_is_omitted_when_blank() -> None:
    with_reason = render_email(
        "payment_rejected", **{**_SAMPLE_CONTEXT["payment_rejected"]}
    )
    assert "Motif" in with_reason.text

    without = render_email(
        "payment_rejected",
        **{**_SAMPLE_CONTEXT["payment_rejected"], "reason": ""},
    )
    assert "Motif" not in without.text


def test_unknown_language_falls_back_to_default() -> None:
    fallback = render_email(
        "order_created", lang="xx", **_SAMPLE_CONTEXT["order_created"]
    )
    default = render_email(
        "order_created", lang=DEFAULT_LANG, **_SAMPLE_CONTEXT["order_created"]
    )
    assert fallback.text == default.text
    assert fallback.subject == default.subject
