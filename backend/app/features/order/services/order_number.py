"""Human-readable order number allocation (M5).

``CMD-{YYYY}-{NNNNN}`` — year of issuance plus a counter drawn from the
dedicated PostgreSQL sequence ``order_number_seq``.

The sequence is deliberately **global** (not reset per year): uniqueness is
guaranteed by construction, and the year prefix stays informative. Gaps are
expected and harmless — ``nextval`` is not transactional, so a rolled-back
checkout burns a number. This is a communication reference, never an
accounting one; the invoice number (M3) uses a separate, gap-free counter.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.notification.email_renderer import short_ref
from app.features.order.models.order import Order, order_number_seq

ORDER_NUMBER_SEQUENCE = order_number_seq.name
ORDER_NUMBER_PREFIX = "CMD"
_COUNTER_WIDTH = 5


def format_order_number(counter: int, *, year: int) -> str:
    """Format a raw counter into ``CMD-{year}-{counter}`` (zero-padded)."""
    return f"{ORDER_NUMBER_PREFIX}-{year}-{counter:0{_COUNTER_WIDTH}d}"


async def allocate_order_number(
    session: AsyncSession, *, now: datetime | None = None
) -> str:
    """Draw the next order number from the sequence.

    Safe under concurrency (``nextval`` never hands the same value twice) and
    non-blocking (no row lock), at the cost of gaps on rollback.
    """
    result = await session.execute(order_number_seq.next_value().select())
    counter = int(result.scalar_one())
    reference_date = now or datetime.now(timezone.utc)
    return format_order_number(counter, year=reference_date.year)


async def resolve_order_ref(session: AsyncSession, payload: dict[str, Any]) -> str:
    """Customer-facing order reference for emails and documents.

    Prefers the payload's ``order_number``, then the order's stored number,
    and finally the UUID-derived short ref (orders created before M5).
    """
    number = payload.get("order_number")
    if isinstance(number, str) and number.strip():
        return number.strip()

    raw_order_id = payload.get("order_id")
    if not raw_order_id:
        return ""

    try:
        order = await session.get(Order, uuid.UUID(str(raw_order_id)))
    except (TypeError, ValueError):
        order = None
    if order is not None and order.order_number:
        return order.order_number
    return short_ref(raw_order_id)
