import uuid
from collections.abc import AsyncGenerator, Generator
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.core.db import get_db
from app.features.base.crud import RecordNotFoundError
from app.features.product.crud.product import crud_product
from app.main import app


@pytest.fixture
def db_session() -> SimpleNamespace:
    return SimpleNamespace()


@pytest.fixture(autouse=True)
def override_dependencies(
    db_session: SimpleNamespace,
) -> Generator[None, None, None]:
    async def _override_get_db() -> AsyncGenerator[SimpleNamespace, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.clear()


def test_get_one_product_missing_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product_id = uuid.uuid4()

    monkeypatch.setattr(
        crud_product,
        "read",
        AsyncMock(side_effect=RecordNotFoundError("missing product")),
    )

    response = client.get(f"/api/v1/product/{product_id}")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "product.not_found",
            "message": "Product not found",
            "details": {
                "product_id": str(product_id),
                "reason": "record_not_found",
            },
        }
    }


def test_get_one_product_not_enriched_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product_id = uuid.uuid4()

    monkeypatch.setattr(
        crud_product,
        "read",
        AsyncMock(
            return_value=SimpleNamespace(
                id=product_id, is_enriched=False, is_supplier_managed=True
            )
        ),
    )

    response = client.get(f"/api/v1/product/{product_id}")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "product.not_found",
            "message": "Product not found",
            "details": {
                "product_id": str(product_id),
                "reason": "not_enriched",
            },
        }
    }
