"""Unit checks of the low-severity points left by the review of the
November 2026 audit fixes."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.core.http_retry import redact_secrets
from app.core.webhook import allowed_webhook_url
from app.features.payment.services.gift_cards import _issued_amount


def _line(unit_price: str, quantity: int = 1, discount: str = "0") -> Any:
    return cast(
        Any,
        SimpleNamespace(
            unit_price=Decimal(unit_price),
            quantity=quantity,
            discount_amount=Decimal(discount),
        ),
    )


def test_a_gift_card_is_never_worth_more_than_it_cost() -> None:
    face = Decimal("10000")
    assert _issued_amount(face, _line("10000")) == face
    # Sold for less by a quote: worth what was paid.
    assert _issued_amount(face, _line("8000")) == Decimal("8000")
    assert _issued_amount(face, _line("10000", 2, "4000")) == Decimal("8000")
    # Sold above its value (a fee in the price): the face value.
    assert _issued_amount(face, _line("10500")) == face
    # A free line (offered by the shop) keeps its face value.
    assert _issued_amount(face, _line("0")) == face


def test_an_error_quoting_a_url_does_not_log_its_key() -> None:
    text = (
        "0, message='x', url='https://live.icecat.biz/api?lang=fr&app_key=S3CR3T&ean=4'"
    )
    assert "S3CR3T" not in redact_secrets(text)
    assert "ean=4" in redact_secrets(text)


def test_an_ip_literal_on_the_allow_list_is_not_a_webhook_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The connector checks what a name resolves to; an IP literal skips
    that check."""
    from app.core.config import settings

    monkeypatch.setattr(
        settings, "OUTBOUND_WEBHOOK_ALLOWED_HOSTS", ["127.0.0.1", "hooks.zapier.com"]
    )
    assert allowed_webhook_url("https://127.0.0.1/x") is None
    assert allowed_webhook_url("https://hooks.zapier.com/x") is not None


def test_the_fiscal_year_is_the_shops_calendar_year(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Functional audit, November 2026: issued in UTC, a document of
    31 December after 14:00 at Tahiti took the next year's number."""
    from datetime import UTC, datetime

    from app.core.config import settings
    from app.features.invoice.services.numbering import fiscal_year_of

    monkeypatch.setattr(settings, "SHOP_TIMEZONE", "Pacific/Tahiti")
    # 31/12/2026 at 20:00 in Tahiti is 01/01/2027 06:00 UTC.
    assert fiscal_year_of(datetime(2027, 1, 1, 6, 0, tzinfo=UTC)) == 2026
    assert fiscal_year_of(datetime(2027, 1, 1, 11, 0, tzinfo=UTC)) == 2027
