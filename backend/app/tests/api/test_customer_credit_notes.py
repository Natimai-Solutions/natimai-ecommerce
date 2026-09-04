"""Customer-facing credit-note endpoints.

A customer who has been refunded is entitled to the document that says so, not
just to the money. The other thing these check is ownership: someone else's
credit note must be reported as missing, never as forbidden, or the ids become
probeable.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.api.routes import invoices_me
from app.api.routes.invoices_me import (
    download_my_credit_note_pdf,
    list_my_credit_notes,
    list_my_credit_notes_for_order,
)
from app.core.errors import AppError
from app.features.invoice.models.credit_note import CreditNote
from app.features.invoice.services.pdf import PdfRenderingUnavailableError


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _user() -> Any:
    return SimpleNamespace(id=uuid.uuid4())


def _note(user_id: uuid.UUID, *, number: str = "AV-2026-00001", **kw: Any) -> Any:
    base: dict[str, Any] = {
        "id": uuid.uuid4(),
        "credit_note_number": number,
        "fiscal_year": 2026,
        "invoice_id": uuid.uuid4(),
        "order_id": uuid.uuid4(),
        "user_id": user_id,
        "issued_at": datetime(2026, 8, 27, tzinfo=timezone.utc),
        "currency": "XPF",
        "total_excl_tax": Decimal("1000.00"),
        "total_tax": Decimal("130.00"),
        "total_incl_tax": Decimal("1130.00"),
        "reason": "Article retourné",
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _session_returning(notes: list[Any]) -> Any:
    session = AsyncMock()
    session.exec = AsyncMock(return_value=SimpleNamespace(all=lambda: notes))
    return session


@pytest.mark.anyio
async def test_a_customer_sees_their_credit_notes() -> None:
    user = _user()
    result = await list_my_credit_notes(
        session=_session_returning([_note(user.id)]), current_user=user
    )

    assert len(result) == 1
    assert result[0].credit_note_number == "AV-2026-00001"
    assert result[0].total_incl_tax == Decimal("1130.00")


@pytest.mark.anyio
async def test_an_order_can_carry_several_credit_notes() -> None:
    """A partial refund can be followed by another; each gets its own note."""
    user = _user()
    order_id = uuid.uuid4()
    session = _session_returning(
        [
            _note(user.id, number="AV-2026-00001", order_id=order_id),
            _note(user.id, number="AV-2026-00002", order_id=order_id),
        ]
    )
    session.get = AsyncMock(return_value=SimpleNamespace(user_id=user.id))

    result = await list_my_credit_notes_for_order(
        session=session, order_id=order_id, current_user=user
    )

    assert [note.credit_note_number for note in result] == [
        "AV-2026-00001",
        "AV-2026-00002",
    ]


@pytest.mark.anyio
async def test_someone_elses_order_is_reported_as_missing() -> None:
    """404 rather than 403, so order ids cannot be probed."""
    session = AsyncMock()
    session.get = AsyncMock(return_value=SimpleNamespace(user_id=uuid.uuid4()))

    with pytest.raises(AppError) as excinfo:
        await list_my_credit_notes_for_order(
            session=session, order_id=uuid.uuid4(), current_user=_user()
        )

    assert excinfo.value.status_code == 404


@pytest.mark.anyio
async def test_someone_elses_credit_note_is_reported_as_missing() -> None:
    session = AsyncMock()
    session.get = AsyncMock(return_value=_note(uuid.uuid4()))

    with pytest.raises(AppError) as excinfo:
        await download_my_credit_note_pdf(
            session=session, credit_note_id=uuid.uuid4(), current_user=_user()
        )

    assert excinfo.value.status_code == 404
    assert excinfo.value.code == "credit_note.not_found"


@pytest.mark.anyio
async def test_the_owner_downloads_the_pdf(monkeypatch: pytest.MonkeyPatch) -> None:
    user = _user()
    note = _note(user.id)
    session = AsyncMock()
    session.get = AsyncMock(return_value=note)
    monkeypatch.setattr(invoices_me, "render_credit_note_pdf", lambda _n: b"%PDF-1.7")

    response = await download_my_credit_note_pdf(
        session=session, credit_note_id=note.id, current_user=user
    )

    assert response.media_type == "application/pdf"
    assert "AV-2026-00001.pdf" in response.headers["Content-Disposition"]


@pytest.mark.anyio
async def test_a_deployment_without_weasyprint_answers_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _user()
    note = _note(user.id)
    session = AsyncMock()
    session.get = AsyncMock(return_value=note)

    def _boom(_note: CreditNote) -> bytes:
        raise PdfRenderingUnavailableError("no pango here")

    monkeypatch.setattr(invoices_me, "render_credit_note_pdf", _boom)

    with pytest.raises(AppError) as excinfo:
        await download_my_credit_note_pdf(
            session=session, credit_note_id=note.id, current_user=user
        )

    assert excinfo.value.status_code == 503
