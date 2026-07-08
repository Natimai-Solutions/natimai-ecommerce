import uuid
from collections.abc import AsyncGenerator, Generator
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.core.db import get_db
from app.features.discount.crud import crud_discount
from app.main import app


@pytest.fixture
def current_user() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), is_superuser=False, is_active=True)


@pytest.fixture
def db_session() -> SimpleNamespace:
    return SimpleNamespace()


@pytest.fixture(autouse=True)
def override_dependencies(
    current_user: SimpleNamespace,
    db_session: SimpleNamespace,
) -> Generator[None, None, None]:
    async def _override_current_user() -> SimpleNamespace:
        return current_user

    async def _override_get_db() -> AsyncGenerator[SimpleNamespace, None]:
        yield db_session

    app.dependency_overrides[get_current_user] = _override_current_user
    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.clear()


def test_validate_coupon_invalid_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        crud_discount,
        "validate_coupon",
        AsyncMock(return_value=(False, "Code coupon invalide", None)),
    )

    response = client.post(
        "/api/v1/discount/validate-coupon",
        params={"code": "BAD-CODE"},
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "discount.coupon.invalid",
            "message": "Code coupon invalide",
            "details": {
                "coupon_code": "BAD-CODE",
                "reason": "Code coupon invalide",
            },
        }
    }


def test_use_discount_not_found_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    current_user: SimpleNamespace,
) -> None:
    discount_id = uuid.uuid4()
    # Consuming a usage is admin-only since the gating pass.
    current_user.is_superuser = True

    monkeypatch.setattr(
        crud_discount,
        "increment_usage",
        AsyncMock(return_value=None),
    )

    response = client.post(f"/api/v1/discount/{discount_id}/use")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "discount.not_found",
            "message": "R\u00e9duction non trouv\u00e9e",
            "details": {"discount_id": str(discount_id)},
        }
    }
