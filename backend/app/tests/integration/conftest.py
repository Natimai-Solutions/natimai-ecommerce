"""Integration-test harness: a REAL Postgres session against a throwaway test
database, with the full schema created per test.

These tests catch issues unit tests (mocked sessions) cannot — notably the
"ORM attribute accessed after an internal commit" → MissingGreenlet class of
bugs, since they run against a real async engine.

Configure the DB via ``TEST_DATABASE_URL`` (defaults to a local ``…_test`` db).
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import AsyncGenerator, Callable
from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

# psycopg's async mode is incompatible with Windows' default ProactorEventLoop.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Import every model so SQLModel.metadata is fully populated before create_all.
from app.features.models import *  # noqa: E402,F401,F403

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/fastapi_ecommerce_test",
)
STRICT_INTEGRATION_DB = os.environ.get(
    "STRICT_INTEGRATION_DB", "0"
).strip().lower() in {"1", "true", "yes", "on"}


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """A real async session on a freshly-created schema (clean slate per test)."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    # DROP SCHEMA … CASCADE rather than metadata.drop_all: the models have a
    # circular FK (users ↔ price_groups) that drop_all cannot topologically sort.
    try:
        async with engine.begin() as conn:
            await conn.exec_driver_sql("DROP SCHEMA public CASCADE")
            await conn.exec_driver_sql("CREATE SCHEMA public")
            await conn.run_sync(SQLModel.metadata.create_all)
    except (OperationalError, InterfaceError, OSError) as exc:
        # No reachable test database (e.g. a local run without the stack up).
        # Skip by default so the unit suite stays runnable everywhere.
        # In CI, enable STRICT_INTEGRATION_DB=1 to fail hard instead of skipping.
        await engine.dispose()
        if STRICT_INTEGRATION_DB:
            pytest.fail(f"integration test database unavailable: {exc}")
        pytest.skip(f"integration test database unavailable: {exc}")
    try:
        async with AsyncSession(engine) as session:
            yield session
    finally:
        await engine.dispose()


@pytest.fixture
def freeze_departure_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[datetime], None]:
    """Pin the clock of the grouped departures (``departure.crud.utcnow`` and
    every module that imported it by name) to a fixed instant.

    Tests written around a fixed date (cutoffs ``NOW + n days``) otherwise
    break once the real date passes them: the next open departure and the
    reminders still to come are decided against the real clock.
    """
    from app.api.routes import admin_grouped_departures
    from app.features.departure import crud, reception, services

    def freeze(now: datetime) -> None:
        for module in (crud, services, reception, admin_grouped_departures):
            monkeypatch.setattr(module, "utcnow", lambda: now)

    return freeze
