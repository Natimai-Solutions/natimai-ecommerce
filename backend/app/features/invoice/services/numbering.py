"""Gap-free invoice numbering (M3).

``FAC-{YYYY}-{NNNNN}``, restarting at 1 each fiscal year.

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
_COUNTER_WIDTH = 5


def format_invoice_number(counter: int, *, fiscal_year: int) -> str:
    """Format a raw counter into ``FAC-{year}-{counter}`` (zero-padded)."""
    return f"{INVOICE_NUMBER_PREFIX}-{fiscal_year}-{counter:0{_COUNTER_WIDTH}d}"


async def allocate_invoice_number(
    session: AsyncSession, *, fiscal_year: int
) -> tuple[str, int]:
    """Allocate the next invoice number for ``fiscal_year``.

    Returns ``(invoice_number, sequence_number)``. Must be called inside the
    transaction that persists the invoice — the number is only definitive once
    that transaction commits.
    """
    # Create the year's counter on first use; concurrent callers converge on
    # the same row (the loser of the race simply finds it already there).
    await session.execute(
        text(
            "INSERT INTO invoice_counters (fiscal_year, last_value) "
            "VALUES (:year, 0) ON CONFLICT (fiscal_year) DO NOTHING"
        ),
        {"year": fiscal_year},
    )

    result = await session.execute(
        text(
            "SELECT last_value FROM invoice_counters "
            "WHERE fiscal_year = :year FOR UPDATE"
        ),
        {"year": fiscal_year},
    )
    last_value = int(result.scalar_one())
    sequence_number = last_value + 1

    await session.execute(
        text(
            "UPDATE invoice_counters SET last_value = :value WHERE fiscal_year = :year"
        ),
        {"value": sequence_number, "year": fiscal_year},
    )

    return format_invoice_number(sequence_number, fiscal_year=fiscal_year), (
        sequence_number
    )
