"""Delivery of the issued credit note to the customer (Z2).

Same contract as the invoice mail: the document was issued and stored, the
customer must be told; ``emailed_at`` keeps an outbox replay from sending it
twice, and a failed delivery raises so ARQ retries.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.handlers import order as handlers


def _note(**overrides: Any) -> SimpleNamespace:
    base = {
        "id": uuid4(),
        "credit_note_number": "AV-2026-00003",
        "invoice_id": uuid4(),
        "order_id": uuid4(),
        "user_id": uuid4(),
        "currency": "XPF",
        "total_incl_tax": Decimal("11300.00"),
        "total_tax": Decimal("1300.00"),
        "reason": "Article retourné",
        "snapshot": {"invoice": {"number": "FAC-2026-00042"}},
        "emailed_at": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _payload(note: SimpleNamespace) -> dict[str, Any]:
    return {
        "credit_note_id": str(note.id),
        "credit_note_number": note.credit_note_number,
        "invoice_id": str(note.invoice_id),
        "order_id": str(note.order_id),
        "user_id": str(note.user_id),
        "currency": note.currency,
        "total_incl_tax": str(note.total_incl_tax),
        "total_tax": str(note.total_tax),
        "reason": note.reason,
    }


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def send(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
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


def _session(note: SimpleNamespace | None) -> Any:
    session = AsyncMock()
    session.add = Mock()
    session.get = AsyncMock(return_value=note)
    return session


@pytest.mark.anyio
async def test_the_credit_note_is_emailed_with_its_references(send: AsyncMock) -> None:
    note = _note()
    session = _session(note)

    await handlers.on_credit_note_issued_customer(cast(Any, session), _payload(note))

    send.assert_awaited_once()
    assert send.await_args is not None
    kwargs = send.await_args.kwargs
    assert "AV-2026-00003" in kwargs["subject"]
    assert "FAC-2026-00042" in kwargs["text"]
    assert "11300.00" in kwargs["text"]
    assert "Article retourné" in kwargs["text"]
    assert "/mon-compte" in kwargs["text"]
    assert kwargs["event_type"] == "credit_note.issued"
    assert note.emailed_at is not None
    session.commit.assert_awaited_once()


@pytest.mark.anyio
async def test_a_replay_does_not_send_it_again(send: AsyncMock) -> None:
    note = _note(emailed_at=datetime.now(UTC))
    await handlers.on_credit_note_issued_customer(
        cast(Any, _session(note)), _payload(note)
    )
    send.assert_not_awaited()


@pytest.mark.anyio
async def test_a_failed_send_raises_so_arq_retries(send: AsyncMock) -> None:
    send.return_value = False
    note = _note()
    with pytest.raises(RuntimeError, match="AV-2026-00003"):
        await handlers.on_credit_note_issued_customer(
            cast(Any, _session(note)), _payload(note)
        )
    assert note.emailed_at is None


@pytest.mark.anyio
async def test_missing_or_malformed_notes_are_skipped(send: AsyncMock) -> None:
    await handlers.on_credit_note_issued_customer(
        cast(Any, _session(None)), _payload(_note())
    )
    for payload in ({}, {"credit_note_id": "nope"}):
        await handlers.on_credit_note_issued_customer(
            cast(Any, _session(None)), payload
        )
    send.assert_not_awaited()
