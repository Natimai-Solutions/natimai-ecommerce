"""Delivery of the issued invoice to the customer.

The invoice was created and stored, and that was the end of it: nothing ever
sent it, so the customer had to know it existed and go and download it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.handlers import order as handlers


def _invoice(**overrides: Any) -> SimpleNamespace:
    base = {
        "id": uuid4(),
        "invoice_number": "FAC-2026-00007",
        "user_id": uuid4(),
        "currency": "XPF",
        "total_incl_tax": Decimal("119000.00"),
        "total_tax": Decimal("19000.00"),
        "emailed_at": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _payload(invoice: SimpleNamespace) -> dict[str, Any]:
    return {
        "invoice_id": str(invoice.id),
        "invoice_number": invoice.invoice_number,
        "order_id": str(uuid4()),
        "user_id": str(invoice.user_id),
        "currency": invoice.currency,
        "total_incl_tax": str(invoice.total_incl_tax),
        "total_tax": str(invoice.total_tax),
    }


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def send(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Intercept the outbound e-mail; delivered unless a test says otherwise."""
    mock = AsyncMock(return_value=True)
    monkeypatch.setattr(handlers, "_send_order_email", mock)
    monkeypatch.setattr(
        handlers, "_resolve_order_ref", AsyncMock(return_value="CMD-2026-00042")
    )
    monkeypatch.setattr(
        handlers,
        "_resolve_user_from_payload",
        AsyncMock(return_value=SimpleNamespace(full_name="Client", email="c@test.pf")),
    )
    return mock


@pytest.mark.anyio
async def test_invoice_is_emailed_to_the_customer(send: AsyncMock) -> None:
    invoice = _invoice()
    session = AsyncMock()
    session.add = Mock()
    session.get = AsyncMock(return_value=invoice)

    await handlers.on_invoice_issued_customer(cast(Any, session), _payload(invoice))

    send.assert_awaited_once()
    assert send.await_args is not None
    kwargs = send.await_args.kwargs
    assert "FAC-2026-00007" in kwargs["subject"]
    assert "FAC-2026-00007" in kwargs["text"]
    assert "119000.00" in kwargs["text"]


@pytest.mark.anyio
async def test_delivery_is_recorded_on_the_invoice(send: AsyncMock) -> None:
    """Without this mark, an outbox replay would mail the invoice twice."""
    assert send.return_value is True  # the fixture makes delivery succeed
    invoice = _invoice()
    session = AsyncMock()
    session.add = Mock()
    session.get = AsyncMock(return_value=invoice)

    await handlers.on_invoice_issued_customer(cast(Any, session), _payload(invoice))

    assert invoice.emailed_at is not None
    session.commit.assert_awaited_once()


@pytest.mark.anyio
async def test_a_replay_does_not_send_it_again(send: AsyncMock) -> None:
    invoice = _invoice(emailed_at=datetime.now(timezone.utc))
    session = AsyncMock()
    session.add = Mock()
    session.get = AsyncMock(return_value=invoice)

    await handlers.on_invoice_issued_customer(cast(Any, session), _payload(invoice))

    send.assert_not_awaited()


@pytest.mark.anyio
async def test_a_failed_send_raises_so_arq_retries(send: AsyncMock) -> None:
    """A legal document must not be lost to a transient provider outage."""
    send.return_value = False
    invoice = _invoice()
    session = AsyncMock()
    session.add = Mock()
    session.get = AsyncMock(return_value=invoice)

    with pytest.raises(RuntimeError, match="FAC-2026-00007"):
        await handlers.on_invoice_issued_customer(cast(Any, session), _payload(invoice))

    # Left unset on purpose, so the retry actually re-sends.
    assert invoice.emailed_at is None


@pytest.mark.anyio
async def test_a_missing_invoice_is_skipped_not_retried_forever(
    send: AsyncMock,
) -> None:
    session = AsyncMock()
    session.add = Mock()
    session.get = AsyncMock(return_value=None)

    await handlers.on_invoice_issued_customer(cast(Any, session), _payload(_invoice()))

    send.assert_not_awaited()


@pytest.mark.anyio
async def test_a_malformed_payload_is_skipped(send: AsyncMock) -> None:
    session = AsyncMock()
    session.add = Mock()

    for payload in ({}, {"invoice_id": "not-a-uuid"}):
        await handlers.on_invoice_issued_customer(cast(Any, session), payload)

    send.assert_not_awaited()


@pytest.mark.anyio
async def test_the_email_links_to_the_account_page(send: AsyncMock) -> None:
    """The PDF needs WeasyPrint's system libraries; the link never fails."""
    invoice = _invoice()
    session = AsyncMock()
    session.add = Mock()
    session.get = AsyncMock(return_value=invoice)

    await handlers.on_invoice_issued_customer(cast(Any, session), _payload(invoice))

    assert send.await_args is not None
    assert "/mon-compte" in send.await_args.kwargs["text"]
