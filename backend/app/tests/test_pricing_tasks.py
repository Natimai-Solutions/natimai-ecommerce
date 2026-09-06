"""Unit tests for the materialized-price refresh triggers.

* ``trigger_price_refresh`` enqueues one ARQ job per scope and absorbs a
  duplicate fired within the dedup window;
* ``schedule_price_refresh`` never raises (a queue outage must not fail an
  admin edit);
* the admin routes that change a pricing parameter do schedule a refresh.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api.routes import admin_categories
from app.api.routes.admin_categories import AdminCategoryUpdate, update_category
from app.api.routes.admin_currency_rates import upsert_currency_rate
from app.features.product.models.category import Category
from app.features.product.models.currency_rate import CurrencyRateUpsertRequest
from app.features.user.models.user import User
from app.tasks import pricing_tasks
from app.tasks.pricing_tasks import schedule_price_refresh, trigger_price_refresh
from app.tests.utils.fake_arq import FakeArqRedis


def _admin() -> User:
    return cast(User, SimpleNamespace(id=uuid4()))


@pytest.mark.asyncio
async def test_trigger_enqueues_once_per_scope_within_the_window(
    arq_queue: FakeArqRedis,
) -> None:
    category_id = uuid4()

    first = await trigger_price_refresh(reason="test", category_id=category_id)
    duplicate = await trigger_price_refresh(
        reason="test-again", category_id=category_id
    )
    whole = await trigger_price_refresh(reason="fx")

    assert duplicate == first  # absorbed: the queued job id comes back
    assert whole != first
    jobs = arq_queue.jobs_for("refresh_sale_prices_task")
    assert [job["category_id"] for job in jobs] == [str(category_id), None]
    assert jobs[0]["reason"] == "test"
    assert jobs[1]["reason"] == "fx"


@pytest.mark.asyncio
async def test_schedule_is_best_effort(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pricing_tasks,
        "trigger_price_refresh",
        AsyncMock(side_effect=RuntimeError("redis down")),
    )
    assert await schedule_price_refresh(reason="test") is None


@pytest.mark.asyncio
async def test_new_currency_rate_refreshes_the_whole_catalog(
    arq_queue: FakeArqRedis,
) -> None:
    session = AsyncMock()
    session.exec = AsyncMock(
        return_value=SimpleNamespace(first=Mock(return_value=None))
    )
    session.add = Mock()

    await upsert_currency_rate(
        code="eur",
        payload=CurrencyRateUpsertRequest(
            rate_to_reference=Decimal("119.33"), valid_from=date(2026, 9, 1)
        ),
        session=session,
        current_user=_admin(),
    )

    jobs = arq_queue.jobs_for("refresh_sale_prices_task")
    assert len(jobs) == 1
    assert jobs[0]["category_id"] is None
    assert jobs[0]["reason"] == "currency_rate:EUR"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "expected_jobs"),
    [
        (AdminCategoryUpdate(default_margin_rate_pct=Decimal("12")), 1),
        (AdminCategoryUpdate(display_name="Portables"), 0),
    ],
)
async def test_category_update_refreshes_only_for_pricing_fields(
    monkeypatch: pytest.MonkeyPatch,
    arq_queue: FakeArqRedis,
    payload: AdminCategoryUpdate,
    expected_jobs: int,
) -> None:
    category = Category(id=uuid4(), name="NOTEBOOKS", is_active=True)
    monkeypatch.setattr(admin_categories, "_load", AsyncMock(return_value=category))
    monkeypatch.setattr(
        admin_categories, "_item_for", AsyncMock(return_value=cast(Any, "item"))
    )
    session = AsyncMock()
    session.add = Mock()

    await update_category(
        category_id=category.id,
        payload=payload,
        session=session,
        current_user=_admin(),
    )

    jobs = arq_queue.jobs_for("refresh_sale_prices_task")
    assert len(jobs) == expected_jobs
    if expected_jobs:
        assert jobs[0]["category_id"] == str(category.id)
