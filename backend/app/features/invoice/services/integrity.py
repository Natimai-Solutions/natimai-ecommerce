"""Integrity chain of the accounting documents (invoices and credit notes).

Each issued document carries ``chain_hash``: the SHA-256 of the previous
document's hash and of its own content (number, dates, parties, totals and
the frozen ``snapshot`` that the PDF is rendered from). Editing a document
after issuance, deleting one or inserting one in the middle breaks the chain
from that point on, and :func:`verify_chains` says where.

One chain per series and per fiscal year (``FAC-2026-…``, ``AV-2026-…``): the
year's numbering counter is locked while a document is issued, so the
previous document of the series is settled and the chain is built in the
same order as the numbers. The first document of a year starts from a fixed
seed (series and year).

Documents issued before the chain existed are sealed, in number order, by the
next issuance of their series and year (under the same lock); until then
:func:`verify_chains` reports them as unsealed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal, cast

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.invoice.models.credit_note import CreditNote
from app.features.invoice.models.invoice import Invoice

Series = Literal["invoice", "credit_note"]
Document = Invoice | CreditNote

_ALGORITHM_VERSION = "v1"


def _series_of(document: Document) -> Series:
    return "credit_note" if isinstance(document, CreditNote) else "invoice"


def _model_of(series: Series) -> type[Invoice] | type[CreditNote]:
    return CreditNote if series == "credit_note" else Invoice


def _number_of(document: Document) -> str:
    if isinstance(document, CreditNote):
        return document.credit_note_number
    return document.invoice_number


def genesis_hash(series: Series, fiscal_year: int) -> str:
    """The seed the first document of a series and year links to."""
    seed = f"natimai:{_ALGORITHM_VERSION}:{series}:{fiscal_year}"
    return hashlib.sha256(seed.encode()).hexdigest()


class NaiveIssuanceDate(ValueError):
    """``issued_at`` has no time zone: hashed as one instant, stored as another."""


def _canonical_datetime(value: datetime) -> str:
    # Stored as timestamptz, the same instant reads back in UTC. A naive value
    # would be hashed as UTC here but stored in the session's time zone by
    # PostgreSQL: the document would read back altered. Refuse it.
    if value.tzinfo is None:
        raise NaiveIssuanceDate(f"issued_at must be time-zone aware: {value!r}")
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def _canonical_amount(value: Decimal) -> str:
    # The columns keep two decimals: 1000 and 1000.00 are the same amount.
    return str(Decimal(value).quantize(Decimal("0.01")))


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )


def document_content(document: Document) -> dict[str, Any]:
    """What the hash covers: everything that makes the document, nothing that
    is distribution metadata (``emailed_at``) or the chain itself."""
    content: dict[str, Any] = {
        "series": _series_of(document),
        "number": _number_of(document),
        "fiscal_year": document.fiscal_year,
        "sequence_number": document.sequence_number,
        "order_id": str(document.order_id),
        "user_id": str(document.user_id),
        "issued_at": _canonical_datetime(document.issued_at),
        "currency": document.currency,
        "total_excl_tax": _canonical_amount(document.total_excl_tax),
        "total_tax": _canonical_amount(document.total_tax),
        "total_incl_tax": _canonical_amount(document.total_incl_tax),
        "snapshot": document.snapshot,
    }
    if isinstance(document, CreditNote):
        content["invoice_id"] = str(document.invoice_id)
        content["refund_id"] = str(document.refund_id)
        content["reason"] = document.reason
    return content


def compute_hash(document: Document, previous_hash: str) -> str:
    """SHA-256 of the previous hash and of the document's canonical content."""
    payload = f"{previous_hash}\n{_canonical_json(document_content(document))}"
    return hashlib.sha256(payload.encode()).hexdigest()


async def _year_documents(
    session: AsyncSession,
    series: Series,
    fiscal_year: int,
    *,
    before: int | None = None,
    after: int | None = None,
) -> list[Document]:
    model = _model_of(series)
    statement = select(model).where(col(model.fiscal_year) == fiscal_year)
    if before is not None:
        statement = statement.where(col(model.sequence_number) < before)
    if after is not None:
        statement = statement.where(col(model.sequence_number) > after)
    result = await session.exec(statement.order_by(col(model.sequence_number)))
    return [cast(Document, row) for row in result.all()]


async def _last_sealed_before(
    session: AsyncSession, series: Series, fiscal_year: int, before: int
) -> tuple[int, str] | None:
    """Sequence number and hash of the last sealed document before ``before``."""
    model = _model_of(series)
    row = (
        await session.exec(
            select(model.sequence_number, model.chain_hash)
            .where(
                col(model.fiscal_year) == fiscal_year,
                col(model.sequence_number) < before,
                col(model.chain_hash).is_not(None),
            )
            .order_by(col(model.sequence_number).desc())
            .limit(1)
        )
    ).first()
    if row is None:
        return None
    sequence, chain_hash = row
    return int(sequence), str(chain_hash)


async def seal_document(session: AsyncSession, document: Document) -> None:
    """Link ``document`` to the chain of its series and year. Flushes nothing.

    Call it after the number is allocated and before the commit, inside the
    issuing transaction: the year's counter lock is held, so no other document
    of the series and year can be issued in between. Earlier documents of the
    year still unsealed (issued before the chain existed) are sealed first.

    Only the last sealed document's hash is read (two columns); the full rows
    are loaded only for the unsealed tail, which is empty once the chain is
    established.
    """
    series = _series_of(document)
    last = await _last_sealed_before(
        session, series, document.fiscal_year, document.sequence_number
    )
    after, previous = last if last is not None else (None, None)
    if previous is None:
        previous = genesis_hash(series, document.fiscal_year)
    for earlier in await _year_documents(
        session,
        series,
        document.fiscal_year,
        before=document.sequence_number,
        after=after,
    ):
        if earlier.chain_hash is None:
            earlier.previous_hash = previous
            earlier.chain_hash = compute_hash(earlier, previous)
            session.add(earlier)
        previous = earlier.chain_hash
    document.previous_hash = previous
    document.chain_hash = compute_hash(document, previous)


@dataclass(slots=True)
class ChainBreak:
    number: str
    reason: Literal["altered", "relinked", "gap"]


@dataclass(slots=True)
class ChainReport:
    series: Series
    fiscal_year: int
    documents: int
    sealed: int
    breaks: list[ChainBreak] = field(default_factory=list)

    @property
    def intact(self) -> bool:
        return not self.breaks


async def verify_chain(
    session: AsyncSession, series: Series, fiscal_year: int
) -> ChainReport:
    """Recompute the chain of one series and year.

    * ``altered``: the document's content no longer matches its own hash;
    * ``relinked``: it no longer links to the document before it (one was
      deleted, inserted or re-sealed);
    * ``gap``: a sequence number is missing.
    """
    documents = await _year_documents(session, series, fiscal_year)
    report = ChainReport(
        series=series,
        fiscal_year=fiscal_year,
        documents=len(documents),
        sealed=sum(1 for d in documents if d.chain_hash is not None),
    )
    previous: str | None = genesis_hash(series, fiscal_year)
    expected_sequence = 1
    unsealed: list[str] = []
    for document in documents:
        number = _number_of(document)
        if document.sequence_number != expected_sequence:
            report.breaks.append(ChainBreak(number, "gap"))
        expected_sequence = document.sequence_number + 1
        if document.chain_hash is None:
            # Issued before the chain: sealed by the next issuance. A sealed
            # document after it means its hash was removed.
            unsealed.append(number)
            previous = None
            continue
        report.breaks.extend(ChainBreak(n, "altered") for n in unsealed)
        unsealed.clear()
        if previous is not None and document.previous_hash != previous:
            report.breaks.append(ChainBreak(number, "relinked"))
        if compute_hash(document, document.previous_hash or "") != document.chain_hash:
            report.breaks.append(ChainBreak(number, "altered"))
        previous = document.chain_hash
    return report


async def verify_chains(session: AsyncSession) -> list[ChainReport]:
    """Every series and fiscal year that has documents."""
    reports: list[ChainReport] = []
    for series in ("invoice", "credit_note"):
        model = _model_of(series)
        years = (
            await session.exec(
                select(model.fiscal_year).distinct().order_by(col(model.fiscal_year))
            )
        ).all()
        for year in years:
            reports.append(await verify_chain(session, series, int(year)))
    return reports


__all__ = [
    "ChainBreak",
    "ChainReport",
    "NaiveIssuanceDate",
    "compute_hash",
    "document_content",
    "genesis_hash",
    "seal_document",
    "verify_chain",
    "verify_chains",
]
