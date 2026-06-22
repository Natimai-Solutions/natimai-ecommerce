"""Contract test for GET /admin/price-groups (superuser, read-only)."""

import uuid
from collections.abc import AsyncGenerator, Generator
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_active_superuser
from app.core.db import get_db
from app.features.product.models.price_group import PriceGroup
from app.main import app


class _ScalarResult:
    def __init__(self, rows: list[PriceGroup]) -> None:
        self._rows = rows

    def all(self) -> list[PriceGroup]:
        return self._rows


class _FakeSession:
    def __init__(self, rows: list[PriceGroup]) -> None:
        self._rows = rows

    async def exec(self, _stmt: object) -> _ScalarResult:
        return _ScalarResult(self._rows)


@pytest.fixture
def price_groups() -> list[PriceGroup]:
    return [
        PriceGroup(
            id=uuid.uuid4(),
            code="particulier",
            label="Particulier",
            margin_rate_pct=Decimal("30.00"),
            default=True,
            requires_validation=False,
        ),
        PriceGroup(
            id=uuid.uuid4(),
            code="revendeur",
            label="Revendeur",
            margin_rate_pct=Decimal("12.00"),
            default=False,
            requires_validation=True,
        ),
    ]


@pytest.fixture(autouse=True)
def override_dependencies(
    price_groups: list[PriceGroup],
) -> Generator[None, None, None]:
    superuser = SimpleNamespace(id=uuid.uuid4(), is_superuser=True, is_active=True)

    async def _override_superuser() -> SimpleNamespace:
        return superuser

    async def _override_get_db() -> AsyncGenerator[_FakeSession, None]:
        yield _FakeSession(price_groups)

    app.dependency_overrides[get_current_active_superuser] = _override_superuser
    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.clear()


def test_list_price_groups_returns_all(
    client: TestClient,
    price_groups: list[PriceGroup],
) -> None:
    response = client.get("/api/v1/admin/price-groups")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert {g["code"] for g in body["data"]} == {"particulier", "revendeur"}
