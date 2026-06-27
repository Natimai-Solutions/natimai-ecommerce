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
from collections.abc import AsyncGenerator

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
        # Skip rather than fail so the unit suite stays runnable everywhere.
        await engine.dispose()
        pytest.skip(f"integration test database unavailable: {exc}")
    try:
        async with AsyncSession(engine) as session:
            yield session
    finally:
        await engine.dispose()
