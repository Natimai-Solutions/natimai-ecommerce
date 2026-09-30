"""Unit: the abandoned-cart sweep query, the reminder handler and the cron."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import ClauseElement

from app.core.config import settings
from app.features.cart.services import abandonment
from app.handlers import cart as cart_handlers
from app.tasks import cart_tasks


def _sql(statement: ClauseElement) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),  # type: ignore[no-untyped-call]
            compile_kwargs={"literal_binds": True},
        )
    )


def test_sweep_selects_open_quiet_carts_never_reminded() -> None:
    sql = _sql(
        abandonment.abandoned_carts_statement(
            now=datetime(2026, 9, 10, 12, tzinfo=timezone.utc),
            delay_hours=24,
            max_age_days=14,
            limit=200,
        )
    )
    assert "carts.is_checked_out IS false" in sql
    assert "carts.abandonment_reminded_at IS NULL" in sql
    assert "carts.last_activity_at <= '2026-09-09 12:00:00+00:00'" in sql
    assert "carts.last_activity_at >= '2026-08-27 12:00:00+00:00'" in sql
    assert "EXISTS (SELECT * \nFROM cart_items" in sql
    assert "LIMIT 200" in sql


def test_cron_follows_the_delay_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "CART_ABANDONMENT_REMINDER_DELAY_HOURS", 24)
    assert len(cart_tasks.get_cart_abandonment_cron_jobs()) == 1
    monkeypatch.setattr(settings, "CART_ABANDONMENT_REMINDER_DELAY_HOURS", 0)
    assert cart_tasks.get_cart_abandonment_cron_jobs() == []


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _payload(cart_id: Any, user_id: Any) -> dict[str, Any]:
    return {
        "cart_id": str(cart_id),
        "user_id": str(user_id),
        "currency": "XPF",
        "total_amount": "25900.00",
        "items": [
            {
                "product_id": str(uuid4()),
                "name": "Clavier sans fil",
                "quantity": 2,
                "unit_price": "12950.00",
                "line_total": "25900.00",
                "image_url": None,
            }
        ],
    }


@pytest.fixture
def send(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock(return_value=True)
    monkeypatch.setattr(cart_handlers, "_send_order_email", mock)
    monkeypatch.setattr(
        cart_handlers,
        "_resolve_user_from_payload",
        AsyncMock(return_value=SimpleNamespace(full_name="Client", email="c@test.pf")),
    )
    monkeypatch.setattr(
        cart_handlers, "marketing_emails_allowed", AsyncMock(return_value=True)
    )
    return mock


def _session(cart: Any) -> Any:
    session = AsyncMock()
    session.add = Mock()
    session.get = AsyncMock(return_value=cart)
    return session


@pytest.mark.anyio
async def test_reminder_lists_the_lines_and_links_to_the_cart(send: AsyncMock) -> None:
    cart = SimpleNamespace(
        id=uuid4(), user_id=uuid4(), is_checked_out=False, is_active=True
    )
    await cart_handlers.on_cart_abandoned(
        cast(Any, _session(cart)), _payload(cart.id, cart.user_id)
    )
    send.assert_awaited_once()
    assert send.await_args is not None
    kwargs = send.await_args.kwargs
    assert "Clavier sans fil" in kwargs["text"]
    assert "25900.00" in kwargs["text"]
    assert "/panier" in kwargs["text"]
    assert kwargs["event_type"] == "cart.abandoned"


@pytest.mark.anyio
async def test_an_ordered_cart_is_not_reminded(send: AsyncMock) -> None:
    cart = SimpleNamespace(
        id=uuid4(), user_id=uuid4(), is_checked_out=True, is_active=True
    )
    await cart_handlers.on_cart_abandoned(
        cast(Any, _session(cart)), _payload(cart.id, cart.user_id)
    )
    send.assert_not_awaited()


@pytest.mark.anyio
async def test_an_opted_out_customer_is_not_reminded(
    send: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        cart_handlers, "marketing_emails_allowed", AsyncMock(return_value=False)
    )
    cart = SimpleNamespace(
        id=uuid4(), user_id=uuid4(), is_checked_out=False, is_active=True
    )
    await cart_handlers.on_cart_abandoned(
        cast(Any, _session(cart)), _payload(cart.id, cart.user_id)
    )
    send.assert_not_awaited()


@pytest.mark.anyio
async def test_a_failed_send_is_logged_not_retried(send: AsyncMock) -> None:
    """Marketing mail: a provider hiccup must not keep the outbox busy."""
    send.return_value = False
    cart = SimpleNamespace(
        id=uuid4(), user_id=uuid4(), is_checked_out=False, is_active=True
    )
    await cart_handlers.on_cart_abandoned(
        cast(Any, _session(cart)), _payload(cart.id, cart.user_id)
    )
    send.assert_awaited_once()
