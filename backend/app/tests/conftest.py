from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.db import engine
from app.main import app
from app.tests.utils.fake_arq import FakeArqRedis
from app.tests.utils.user import authentication_token_from_email
from app.tests.utils.utils import get_superuser_token_headers


@pytest.fixture(autouse=True)
def arq_queue(monkeypatch: pytest.MonkeyPatch) -> FakeArqRedis:
    """Every job enqueued through ``enqueue_with_dedup`` lands here, not in Redis.

    Admin routes schedule a storefront price refresh after a rate or margin
    change; without this the suite would need a Redis server (or wait for the
    connection retries of the best-effort trigger).
    """
    fake = FakeArqRedis()

    async def _pool() -> FakeArqRedis:
        return fake

    monkeypatch.setattr("app.core.arq_worker.get_redis_pool", _pool)
    return fake


@pytest_asyncio.fixture(scope="session")
async def db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSession(engine) as session:
        yield session
        await session.rollback()


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def superuser_token_headers(client: TestClient) -> dict[str, str]:
    return get_superuser_token_headers(client)


@pytest_asyncio.fixture(scope="module")
async def normal_user_token_headers(
    client: TestClient, db: AsyncSession
) -> dict[str, str]:
    return await authentication_token_from_email(
        client=client, email=settings.EMAIL_TEST_USER, db=db
    )
