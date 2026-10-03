"""Admin credit-note endpoints: listing, lookup, PDF and accounting export.

The export is the part that matters. An accountant reconciles a credit-note
sequence by reading it in order and checking that no number is missing, so the
rows must come out sorted by number and the amounts must use the decimal
separator French accounting software expects.
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from app.api.routes import admin_credit_notes
from app.api.routes.admin_credit_notes import (
    _EXPORT_COLUMNS,
    download_credit_note_pdf,
    export_credit_notes_csv,
    get_credit_note,
    list_credit_notes,
)
from app.core.errors import AppError
from app.features.invoice.models.credit_note import CreditNote
from app.features.invoice.services.pdf import PdfRenderingUnavailableError


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _note(number: str = "AV-2026-00001", **overrides: Any) -> Any:
    base: dict[str, Any] = {
        "id": uuid.uuid4(),
        "credit_note_number": number,
        "fiscal_year": 2026,
        "sequence_number": int(number.rsplit("-", 1)[-1]),
        "invoice_id": uuid.uuid4(),
        "refund_id": uuid.uuid4(),
        "order_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "issued_at": datetime(2026, 8, 27, 10, 30, tzinfo=UTC),
        "currency": "XPF",
        "total_excl_tax": Decimal("1000.00"),
        "total_tax": Decimal("130.00"),
        "total_incl_tax": Decimal("1130.00"),
        "reason": "Article retourné",
        "snapshot": {
            "buyer": {"name": "Jean Client", "email": "jean@example.test"},
            "order": {"number": "CMD-2026-000123"},
            "invoice": {"number": "FAC-2026-00042"},
            "tax_breakdown": [
                {
                    "rate_pct": "13.00",
                    "base_excl_tax": "1000.00",
                    "tax_amount": "130.00",
                }
            ],
        },
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _session_returning(notes: list[Any]) -> Any:
    session = AsyncMock()
    session.exec = AsyncMock(return_value=SimpleNamespace(all=lambda: notes))
    return session


def _admin() -> Any:
    return SimpleNamespace(id=uuid.uuid4(), is_superuser=True)


def _read_csv(body: bytes) -> list[list[str]]:
    text = body.decode("utf-8-sig")
    return list(csv.reader(io.StringIO(text), delimiter=";"))


@pytest.mark.anyio
async def test_listing_exposes_the_public_fields() -> None:
    note = _note()
    result = await list_credit_notes(
        session=_session_returning([note]), _current_user=_admin()
    )

    assert len(result) == 1
    assert result[0].credit_note_number == "AV-2026-00001"
    assert result[0].total_incl_tax == Decimal("1130.00")
    assert result[0].reason == "Article retourné"
    # References for the screens, read from the frozen snapshot.
    assert result[0].order_number == "CMD-2026-000123"
    assert result[0].invoice_number == "FAC-2026-00042"


@pytest.mark.anyio
async def test_lookup_reports_a_missing_note_as_404() -> None:
    session = AsyncMock()
    session.get = AsyncMock(return_value=None)

    with pytest.raises(AppError) as excinfo:
        await get_credit_note(
            session=session, credit_note_id=uuid.uuid4(), _current_user=_admin()
        )

    assert excinfo.value.status_code == 404
    assert excinfo.value.code == "credit_note.not_found"


@pytest.mark.anyio
async def test_export_header_matches_the_declared_columns() -> None:
    response = await export_credit_notes_csv(
        session=_session_returning([_note()]), _current_user=_admin()
    )

    rows = _read_csv(cast(bytes, response.body))
    assert rows[0] == _EXPORT_COLUMNS


@pytest.mark.anyio
async def test_export_uses_a_comma_decimal_separator() -> None:
    """French accounting software rejects a dot."""
    response = await export_credit_notes_csv(
        session=_session_returning([_note()]), _current_user=_admin()
    )

    rows = _read_csv(cast(bytes, response.body))
    line = dict(zip(rows[0], rows[1], strict=True))
    assert line["total_excl_tax"] == "1000,00"
    assert line["total_tax"] == "130,00"
    assert line["total_incl_tax"] == "1130,00"


@pytest.mark.anyio
async def test_export_carries_the_corrected_invoice_number() -> None:
    """A credit note that does not name its invoice cannot be reconciled."""
    response = await export_credit_notes_csv(
        session=_session_returning([_note()]), _current_user=_admin()
    )

    rows = _read_csv(cast(bytes, response.body))
    line = dict(zip(rows[0], rows[1], strict=True))
    assert line["invoice_number"] == "FAC-2026-00042"
    assert line["order_number"] == "CMD-2026-000123"
    assert line["customer_email"] == "jean@example.test"


@pytest.mark.anyio
async def test_export_filename_names_the_fiscal_year() -> None:
    response = await export_credit_notes_csv(
        session=_session_returning([_note()]),
        _current_user=_admin(),
        fiscal_year=2026,
    )

    assert "avoirs-2026.csv" in response.headers["Content-Disposition"]


@pytest.mark.anyio
async def test_export_of_an_empty_year_still_has_its_header() -> None:
    """An empty file with no header looks like a broken export."""
    response = await export_credit_notes_csv(
        session=_session_returning([]), _current_user=_admin()
    )

    rows = _read_csv(cast(bytes, response.body))
    assert rows == [_EXPORT_COLUMNS]


@pytest.mark.anyio
async def test_pdf_download_sets_the_document_number_as_filename(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    note = _note()
    session = AsyncMock()
    session.get = AsyncMock(return_value=note)
    monkeypatch.setattr(
        admin_credit_notes, "render_credit_note_pdf", lambda _n: b"%PDF-1.7"
    )

    response = await download_credit_note_pdf(
        session=session, credit_note_id=note.id, _current_user=_admin()
    )

    assert response.media_type == "application/pdf"
    assert "AV-2026-00001.pdf" in response.headers["Content-Disposition"]


@pytest.mark.anyio
async def test_a_deployment_without_weasyprint_answers_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing system libraries must not surface as a 500 stack trace."""
    note = _note()
    session = AsyncMock()
    session.get = AsyncMock(return_value=note)

    def _boom(_note: CreditNote) -> bytes:
        raise PdfRenderingUnavailableError("no pango here")

    monkeypatch.setattr(admin_credit_notes, "render_credit_note_pdf", _boom)

    with pytest.raises(AppError) as excinfo:
        await download_credit_note_pdf(
            session=session, credit_note_id=note.id, _current_user=_admin()
        )

    assert excinfo.value.status_code == 503
    assert excinfo.value.code == "credit_note.pdf.unavailable"
