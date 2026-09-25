"""Gap-free document numbering (M3 invoices, Z2 credit notes).

``FAC-{YYYY}-{NNNNN}`` for invoices, ``AV-{YYYY}-{NNNNN}`` for credit notes,
each restarting at 1 every fiscal year and each with its own counter table:
the two sequences are legally distinct and must never share numbers.

A legal invoice sequence must be **continuous**: no number may be allocated
and then abandoned. A PostgreSQL sequence cannot provide that (``nextval`` is
non-transactional by design), so the counter lives in a table row that is
locked with ``SELECT … FOR UPDATE`` inside the issuing transaction — if that
transaction rolls back, the increment rolls back with it.

The lock serializes concurrent issuances for the same year, which is the
intended behaviour: invoice numbers must also be chronological.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

INVOICE_NUMBER_PREFIX = "FAC"
CREDIT_NOTE_NUMBER_PREFIX = "AV"
QUOTE_NUMBER_PREFIX = "DEV"
_COUNTER_WIDTH = 5

#: Only these table names are ever interpolated into the SQL below.
_INVOICE_COUNTER_TABLE = "invoice_counters"
_CREDIT_NOTE_COUNTER_TABLE = "credit_note_counters"
_QUOTE_COUNTER_TABLE = "quote_counters"


def _format_number(counter: int, *, prefix: str, fiscal_year: int) -> str:
    return f"{prefix}-{fiscal_year}-{counter:0{_COUNTER_WIDTH}d}"


def format_invoice_number(counter: int, *, fiscal_year: int) -> str:
    """Format a raw counter into ``FAC-{year}-{counter}`` (zero-padded)."""
    return _format_number(
        counter, prefix=INVOICE_NUMBER_PREFIX, fiscal_year=fiscal_year
    )


def format_credit_note_number(counter: int, *, fiscal_year: int) -> str:
    """Format a raw counter into ``AV-{year}-{counter}`` (zero-padded)."""
    return _format_number(
        counter, prefix=CREDIT_NOTE_NUMBER_PREFIX, fiscal_year=fiscal_year
    )


async def _allocate_from_counter(
    session: AsyncSession, *, table: str, fiscal_year: int
) -> int:
    """Take the next value of ``table`` for ``fiscal_year`` under a row lock.

    ``table`` is never caller-supplied — the two module constants above are the
    only values it ever takes.
    """
    # Create the year's counter on first use; concurrent callers converge on
    # the same row (the loser of the race simply finds it already there).
    await session.execute(
        text(
            f"INSERT INTO {table} (fiscal_year, last_value) "  # noqa: S608
            "VALUES (:year, 0) ON CONFLICT (fiscal_year) DO NOTHING"
        ),
        {"year": fiscal_year},
    )

    result = await session.execute(
        text(
            f"SELECT last_value FROM {table} "  # noqa: S608
            "WHERE fiscal_year = :year FOR UPDATE"
        ),
        {"year": fiscal_year},
    )
    sequence_number = int(result.scalar_one()) + 1

    await session.execute(
        text(
            f"UPDATE {table} SET last_value = :value "  # noqa: S608
            "WHERE fiscal_year = :year"
        ),
        {"value": sequence_number, "year": fiscal_year},
    )
    return sequence_number


async def allocate_invoice_number(
    session: AsyncSession, *, fiscal_year: int
) -> tuple[str, int]:
    """Allocate the next invoice number for ``fiscal_year``.

    Returns ``(invoice_number, sequence_number)``. Must be called inside the
    transaction that persists the invoice — the number is only definitive once
    that transaction commits.
    """
    sequence_number = await _allocate_from_counter(
        session, table=_INVOICE_COUNTER_TABLE, fiscal_year=fiscal_year
    )
    return (
        format_invoice_number(sequence_number, fiscal_year=fiscal_year),
        sequence_number,
    )


async def allocate_quote_number(session: AsyncSession, *, fiscal_year: int) -> str:
    """Allocate the next quote number (``DEV-{year}-{counter}``).

    A quote is not an accounting document, but the same locked counter gives
    it a readable, chronological number for free.
    """
    sequence_number = await _allocate_from_counter(
        session, table=_QUOTE_COUNTER_TABLE, fiscal_year=fiscal_year
    )
    return _format_number(
        sequence_number, prefix=QUOTE_NUMBER_PREFIX, fiscal_year=fiscal_year
    )


async def allocate_credit_note_number(
    session: AsyncSession, *, fiscal_year: int
) -> tuple[str, int]:
    """Allocate the next credit-note number for ``fiscal_year``.

    Same contract and same guarantees as the invoice sequence, on its own
    counter — the two must never interleave.
    """
    sequence_number = await _allocate_from_counter(
        session, table=_CREDIT_NOTE_COUNTER_TABLE, fiscal_year=fiscal_year
    )
    return (
        format_credit_note_number(sequence_number, fiscal_year=fiscal_year),
        sequence_number,
    )
