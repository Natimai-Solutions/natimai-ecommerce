from collections.abc import AsyncGenerator, Generator
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_active_superuser
from app.api.routes import icecat as icecat_routes
from app.core.config import settings
from app.core.db import get_db
from app.main import app
from app.services.icecat_service import icecat_service


@pytest.fixture
def current_superuser() -> SimpleNamespace:
    return SimpleNamespace(id="admin", is_superuser=True, is_active=True)


@pytest.fixture
def db_session() -> SimpleNamespace:
    return SimpleNamespace()


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


@pytest.fixture(autouse=True)
def icecat_module_on(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """The fake session cannot be queried: the module switch is stubbed."""
    switch = AsyncMock(return_value=True)
    monkeypatch.setattr(icecat_routes, "module_enabled", switch)
    return switch


def test_icecat_enrich_switched_off_in_admin_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    icecat_module_on: AsyncMock,
) -> None:
    monkeypatch.setattr(settings, "ICECAT_ENABLED", True)
    icecat_module_on.return_value = False

    response = client.post("/api/v1/icecat/enrich", json={"product_id": "P1"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "icecat.disabled"
    assert response.json()["error"]["details"] == {"setting": "module.icecat"}


def test_icecat_enrich_disabled_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ICECAT_ENABLED", False)

    response = client.post("/api/v1/icecat/enrich", json={"product_id": "P1"})

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "icecat.disabled",
            "message": "Icecat enrichment is disabled in settings",
            "details": {"setting": "ICECAT_ENABLED"},
        }
    }


def test_icecat_enrich_queue_failed_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ICECAT_ENABLED", True)
    monkeypatch.setattr(
        icecat_routes,
        "trigger_product_enrichment",
        AsyncMock(side_effect=RuntimeError("arq down")),
    )

    response = client.post("/api/v1/icecat/enrich", json={"product_id": "P1"})

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "icecat.enrich.queue_failed",
            "message": "Failed to queue enrichment job: arq down",
            "details": {
                "product_id": "P1",
                "reason": "arq down",
            },
        }
    }


def test_icecat_batch_queue_failed_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ICECAT_ENABLED", True)
    monkeypatch.setattr(
        icecat_routes,
        "trigger_batch_enrichment",
        AsyncMock(side_effect=RuntimeError("queue blocked")),
    )

    response = client.post("/api/v1/icecat/enrich/batch", json={"limit": 20})

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "icecat.batch.queue_failed",
            "message": "Failed to queue batch enrichment job: queue blocked",
            "details": {
                "limit": 20,
                "reason": "queue blocked",
            },
        }
    }


def test_icecat_test_endpoint_failure_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ICECAT_ENABLED", True)
    monkeypatch.setattr(
        icecat_service,
        "enrich_product_with_icecat",
        AsyncMock(side_effect=RuntimeError("upstream timeout")),
    )

    response = client.post(
        "/api/v1/icecat/test",
        json={
            "vendor_part_number": "VP-123",
            "manufacturer": "Acme",
            "ean": "1234567890123",
            "upc": "123456789012",
        },
    )

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "icecat.test.failed",
            "message": "Icecat API test failed: upstream timeout",
            "details": {
                "vendor_part_number": "VP-123",
                "manufacturer": "Acme",
                "ean": "1234567890123",
                "upc": "123456789012",
                "reason": "upstream timeout",
            },
        }
    }


def test_icecat_search_upc_failure_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ICECAT_ENABLED", True)
    monkeypatch.setattr(
        icecat_service,
        "get_product_by_upc",
        AsyncMock(side_effect=RuntimeError("upc endpoint error")),
    )

    response = client.get("/api/v1/icecat/search/upc/123456789012")

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "icecat.search.upc.failed",
            "message": "UPC search failed: upc endpoint error",
            "details": {
                "upc": "123456789012",
                "reason": "upc endpoint error",
            },
        }
    }


def test_icecat_search_ean_failure_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ICECAT_ENABLED", True)
    monkeypatch.setattr(
        icecat_service,
        "get_product_by_ean",
        AsyncMock(side_effect=RuntimeError("ean endpoint error")),
    )

    response = client.get("/api/v1/icecat/search/ean/1234567890123")

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "icecat.search.ean.failed",
            "message": "EAN search failed: ean endpoint error",
            "details": {
                "ean": "1234567890123",
                "reason": "ean endpoint error",
            },
        }
    }


def test_icecat_admin_endpoints_require_authentication(client: TestClient) -> None:
    """S2 audit fix: /test and /search/* had their superuser dependency
    commented out and were reachable anonymously."""
    app.dependency_overrides.pop(get_current_active_superuser, None)

    response = client.post(
        "/api/v1/icecat/test",
        json={
            "vendor_part_number": "VP-123",
            "manufacturer": "Acme",
            "ean": "1234567890123",
            "upc": "123456789012",
        },
    )
    assert response.status_code == 401

    assert client.get("/api/v1/icecat/search/upc/123456789012").status_code == 401
    assert client.get("/api/v1/icecat/search/ean/1234567890123").status_code == 401
