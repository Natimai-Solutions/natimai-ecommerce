"""Integration tests: the integrity chain of invoices and credit notes.

Real DB — the chain must survive the round trip through PostgreSQL
(timestamptz, numeric(12,2), JSON) and is built under the numbering lock.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.invoice.models.invoice import Invoice
from app.features.invoice.services.integrity import (
    NaiveIssuanceDate,
    compute_hash,
    genesis_hash,
    verify_chain,
    verify_chains,
)
from app.features.invoice.services.invoice_service import issue_invoice_for_order
from app.features.invoice.services.numbering import allocate_invoice_number
from app.tests.integration.test_invoice_issuance import _seed_paid_order

_ISSUED = datetime(2026, 5, 6, 7, 8, 9, 123456, tzinfo=UTC)


async def _issue(session: AsyncSession) -> uuid.UUID:
    order = await _seed_paid_order(session)
    invoice = await issue_invoice_for_order(
        session, order_id=order.id, issued_at=_ISSUED
    )
    invoice_id: uuid.UUID = invoice.id
    return invoice_id


async def _reload(session: AsyncSession, invoice_id: uuid.UUID) -> Invoice:
    session.expire_all()
    invoice = await session.get(Invoice, invoice_id)
    assert invoice is not None
    return invoice


@pytest.mark.asyncio
async def test_issued_invoices_form_an_intact_chain(db_session: AsyncSession) -> None:
    first_id = await _issue(db_session)
    second_id = await _issue(db_session)

    first = await _reload(db_session, first_id)
    first_previous, first_hash = first.previous_hash, first.chain_hash
    second = await _reload(db_session, second_id)
    assert first_previous == genesis_hash("invoice", 2026)
    assert first_hash is not None and len(first_hash) == 64
    assert second.previous_hash == first_hash

    report = await verify_chain(db_session, "invoice", 2026)
    assert (report.documents, report.sealed, report.intact) == (2, 2, True)


@pytest.mark.asyncio
async def test_editing_an_issued_invoice_breaks_the_chain(
    db_session: AsyncSession,
) -> None:
    first_id = await _issue(db_session)
    await _issue(db_session)

    # Straight in the database, as someone bypassing the application would.
    await db_session.execute(
        text("UPDATE invoices SET total_incl_tax = total_incl_tax - 1 WHERE id = :id"),
        {"id": first_id},
    )
    await db_session.commit()

    report = await verify_chain(db_session, "invoice", 2026)
    first = await _reload(db_session, first_id)
    assert not report.intact
    assert [(b.number, b.reason) for b in report.breaks] == [
        (first.invoice_number, "altered")
    ]


@pytest.mark.asyncio
async def test_deleting_an_invoice_is_seen_as_a_gap_and_a_relink(
    db_session: AsyncSession,
) -> None:
    await _issue(db_session)
    middle_id = await _issue(db_session)
    last_id = await _issue(db_session)
    middle = await _reload(db_session, middle_id)
    middle_number = middle.invoice_number
    await db_session.execute(
        text("DELETE FROM invoices WHERE id = :id"), {"id": middle_id}
    )
    await db_session.commit()

    report = await verify_chain(db_session, "invoice", 2026)
    last = await _reload(db_session, last_id)
    assert middle_number not in {b.number for b in report.breaks}
    assert {(b.number, b.reason) for b in report.breaks} == {
        (last.invoice_number, "gap"),
        (last.invoice_number, "relinked"),
    }


@pytest.mark.asyncio
async def test_invoices_issued_before_the_chain_are_sealed_by_the_next_one(
    db_session: AsyncSession,
) -> None:
    # An invoice issued before the chain existed: no hash.
    order = await _seed_paid_order(db_session)
    number, sequence = await allocate_invoice_number(db_session, fiscal_year=2026)
    legacy = Invoice(
        invoice_number=number,
        fiscal_year=2026,
        sequence_number=sequence,
        order_id=order.id,
        user_id=order.user_id,
        issued_at=_ISSUED,
        currency="XPF",
        total_excl_tax=Decimal("100"),
        total_tax=Decimal("16"),
        total_incl_tax=Decimal("116"),
        snapshot={"order": {"number": order.order_number}},
    )
    db_session.add(legacy)
    legacy_id = legacy.id
    await db_session.commit()

    before = await verify_chain(db_session, "invoice", 2026)
    assert (before.documents, before.sealed, before.intact) == (1, 0, True)

    new_id = await _issue(db_session)

    legacy = await _reload(db_session, legacy_id)
    legacy_hash = legacy.chain_hash
    new = await _reload(db_session, new_id)
    assert legacy_hash is not None
    assert new.previous_hash == legacy_hash
    reports = await verify_chains(db_session)
    assert [(r.series, r.fiscal_year, r.sealed, r.intact) for r in reports] == [
        ("invoice", 2026, 2, True)
    ]


def test_a_naive_issuance_date_is_refused() -> None:
    """Hashed as UTC but stored in the session time zone, a naive date would
    read back as an altered document: it is refused at seal time."""
    naive = Invoice(
        invoice_number="FAC-2026-00001",
        fiscal_year=2026,
        sequence_number=1,
        order_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        issued_at=_ISSUED.replace(tzinfo=None),
        currency="XPF",
        total_excl_tax=Decimal("100"),
        total_tax=Decimal("16"),
        total_incl_tax=Decimal("116"),
        snapshot={},
    )
    with pytest.raises(NaiveIssuanceDate):
        compute_hash(naive, genesis_hash("invoice", 2026))
