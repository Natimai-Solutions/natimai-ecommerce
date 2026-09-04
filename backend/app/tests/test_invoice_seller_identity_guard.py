"""An invoice with no seller identity is not an accounting document.

``_seller_identity`` used to log a warning and carry on, so a deployment that
had never filled in its legal identity issued numbered invoices bearing no
trading name, address or registration number. Those numbers come from a
legally gap-free sequence and the document is immutable — there is no way to
take them back.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from app.core.config import settings
from app.features.invoice.services import invoice_service


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _no_alert_webhook(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    alert = AsyncMock(return_value=True)
    monkeypatch.setattr(invoice_service, "send_alert", alert)
    return alert


def _complete() -> dict[str, str]:
    return {
        "legal_trading_name": "Natimai Solutions",
        "legal_head_office_address": "BP 42, Papeete",
        "legal_tahiti_number": "A12345",
        "legal_contact_email": "contact@natimai.pf",
        "legal_contact_phone": "+689 40 00 00 00",
    }


def _with_identity(monkeypatch: pytest.MonkeyPatch, identity: dict[str, str]) -> None:
    monkeypatch.setattr(
        invoice_service, "load_legal_identity", AsyncMock(return_value=identity)
    )
    for name in (
        "INVOICE_SELLER_NAME",
        "INVOICE_SELLER_ADDRESS",
        "INVOICE_SELLER_REGISTRATION",
        "INVOICE_SELLER_EMAIL",
        "INVOICE_SELLER_PHONE",
    ):
        monkeypatch.setattr(settings, name, "", raising=False)


@pytest.mark.anyio
async def test_a_complete_identity_is_returned(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    _with_identity(monkeypatch, _complete())

    identity = await invoice_service._seller_identity(cast(Any, AsyncMock()))

    assert identity["name"] == "Natimai Solutions"
    assert identity["address"] == "BP 42, Papeete"
    assert identity["registration"] == "A12345"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "dropped",
    ["legal_trading_name", "legal_head_office_address", "legal_tahiti_number"],
)
async def test_each_mandatory_field_blocks_issuance(
    monkeypatch: pytest.MonkeyPatch, dropped: str
) -> None:
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    identity = _complete()
    identity[dropped] = ""
    _with_identity(monkeypatch, identity)

    with pytest.raises(invoice_service.InvoiceIssuanceError):
        await invoice_service._seller_identity(cast(Any, AsyncMock()))


@pytest.mark.anyio
async def test_the_block_raises_an_operational_alert(
    monkeypatch: pytest.MonkeyPatch, _no_alert_webhook: AsyncMock
) -> None:
    """Nobody reads the logs before a customer complains."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    identity = _complete()
    identity["legal_tahiti_number"] = ""
    _with_identity(monkeypatch, identity)

    with pytest.raises(invoice_service.InvoiceIssuanceError):
        await invoice_service._seller_identity(cast(Any, AsyncMock()))

    _no_alert_webhook.assert_awaited_once()


@pytest.mark.anyio
async def test_local_development_only_warns(
    monkeypatch: pytest.MonkeyPatch, _no_alert_webhook: AsyncMock
) -> None:
    """A dev stack has no reason to carry a real company's details."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "local")
    _with_identity(monkeypatch, {})

    identity = await invoice_service._seller_identity(cast(Any, AsyncMock()))

    assert identity["name"] == ""
    _no_alert_webhook.assert_not_awaited()


@pytest.mark.anyio
async def test_the_environment_fallback_still_satisfies_the_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A deployment configured only through INVOICE_SELLER_* must still invoice."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(
        invoice_service, "load_legal_identity", AsyncMock(return_value={})
    )
    monkeypatch.setattr(settings, "INVOICE_SELLER_NAME", "Natimai Solutions")
    monkeypatch.setattr(settings, "INVOICE_SELLER_ADDRESS", "BP 42, Papeete")
    monkeypatch.setattr(settings, "INVOICE_SELLER_REGISTRATION", "A12345")

    identity = await invoice_service._seller_identity(cast(Any, AsyncMock()))

    assert identity["registration"] == "A12345"


@pytest.mark.anyio
async def test_optional_contact_details_do_not_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Phone and e-mail are nice to have, not a legal minimum."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    identity = _complete()
    identity["legal_contact_email"] = ""
    identity["legal_contact_phone"] = ""
    _with_identity(monkeypatch, identity)

    resolved = await invoice_service._seller_identity(cast(Any, SimpleNamespace()))

    assert resolved["name"] == "Natimai Solutions"
