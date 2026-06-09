from collections.abc import AsyncGenerator, Generator
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_active_superuser
from app.core.db import get_db
from app.main import app


@pytest.fixture
def current_superuser() -> SimpleNamespace:
    return SimpleNamespace(id="admin", is_superuser=True, is_active=True)


@pytest.fixture
def db_session() -> SimpleNamespace:
    result = SimpleNamespace(first=lambda: None)
    return SimpleNamespace(exec=AsyncMock(return_value=result))


@pytest.fixture(autouse=True)
def override_dependencies(
    current_superuser: SimpleNamespace,
    db_session: SimpleNamespace,
) -> Generator[None, None, None]:
    async def _override_current_superuser() -> SimpleNamespace:
        return current_superuser

    async def _override_get_db() -> AsyncGenerator[SimpleNamespace, None]:
        yield db_session

    app.dependency_overrides[get_current_active_superuser] = _override_current_superuser
    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.clear()


def test_get_active_currency_rate_not_found_returns_error_payload(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/admin/currency-rates/usd")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "currency_rate.active.not_found",
            "message": "No active currency rate found for 'USD'",
            "details": {"currency_code": "USD"},
        }
    }


def test_upsert_currency_rate_reference_currency_returns_error_payload(
    client: TestClient,
) -> None:
    response = client.put(
        "/api/v1/admin/currency-rates/XPF",
        json={
            "rate_to_reference": "123.456000",
            "valid_from": "2026-01-01",
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "currency_rate.reference_currency.unsupported",
            "message": "XPF is the reference currency — no conversion rate needed.",
            "details": {"currency_code": "XPF"},
        }
    }
