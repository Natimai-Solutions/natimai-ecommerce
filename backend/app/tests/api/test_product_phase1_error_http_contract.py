import uuid
from collections.abc import AsyncGenerator, Generator
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_active_superuser
from app.core.db import get_db
from app.features.base.crud import RecordNotFoundError
from app.features.product.crud.product import crud_product
from app.main import app


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


def test_feature_product_not_found_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product_id = uuid.uuid4()

    monkeypatch.setattr(
        crud_product,
        "set_featured",
        AsyncMock(side_effect=RecordNotFoundError("missing product")),
    )

    response = client.post(
        f"/api/v1/product/{product_id}/feature",
        json={"featured_position": 1},
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "product.not_found",
            "message": "Product not found",
            "details": {"product_id": str(product_id)},
        }
    }


def test_unfeature_product_not_found_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product_id = uuid.uuid4()

    monkeypatch.setattr(
        crud_product,
        "clear_featured",
        AsyncMock(side_effect=RecordNotFoundError("missing product")),
    )

    response = client.delete(f"/api/v1/product/{product_id}/feature")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "product.not_found",
            "message": "Product not found",
            "details": {"product_id": str(product_id)},
        }
    }
