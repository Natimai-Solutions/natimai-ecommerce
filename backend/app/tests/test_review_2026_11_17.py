"""Relecture du 17/11/2026 des changements de novembre : ce qui ne demande
pas de base (les parcours sur base vivent dans tests/integration)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest

from app.core import task_runs
from app.features.invoice.services.numbering import fiscal_year_of, shop_local
from app.features.order.services.status import (
    OrderStatusTransitionError,
    check_status_transition,
)
from app.features.user.models.address import AddressUpdate


def test_a_document_is_dated_on_the_shop_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """The number followed the local year, the printed date stayed in UTC:
    « FA-2026-… » dated 01/01/2027."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "SHOP_TIMEZONE", "Pacific/Tahiti")
    issued = datetime(2027, 1, 1, 1, 0, tzinfo=UTC)  # 31/12/2026 15:00 at Tahiti
    assert fiscal_year_of(issued) == 2026
    assert shop_local(issued).strftime("%d/%m/%Y") == "31/12/2026"


def test_an_order_under_payment_review_can_be_paid_again() -> None:
    """Once the wrong payment is refunded, the admin puts the order back to
    « à payer »; the lifecycle refused it as « already paid »."""
    check_status_transition("PaymentReview", "AwaitingPayment")
    check_status_transition("PaymentReview", "PaymentFailed")
    with pytest.raises(OrderStatusTransitionError):
        check_status_transition("Delivered", "PaymentFailed")
    with pytest.raises(OrderStatusTransitionError):
        check_status_transition("Refunded", "PartiallyRefunded")


def test_the_address_update_keeps_the_length_limits() -> None:
    with pytest.raises(ValueError):
        AddressUpdate(recipient_name="x" * 151)
    with pytest.raises(ValueError):
        AddressUpdate(phone="1" * 41)


@pytest.mark.anyio
async def test_a_cancelled_task_is_journaled_as_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """arq enforces its timeout by cancelling the task: the run stayed « ok »."""
    recorded: list[tuple[str, str]] = []

    async def start(_name: str) -> None:
        return None

    async def record(name: str, status: str, *_args: Any, **_kwargs: Any) -> None:
        recorded.append((name, status))

    monkeypatch.setattr(task_runs, "_record_start", start)
    monkeypatch.setattr(task_runs, "record_run", record)

    async def slow(_ctx: Any) -> str:
        await asyncio.sleep(30)
        return "ok"

    wrapped = task_runs.journaled(slow, "slow_task")
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(wrapped({}), timeout=0.05)
    assert recorded == [("slow_task", task_runs.STATUS_FAILED)]
