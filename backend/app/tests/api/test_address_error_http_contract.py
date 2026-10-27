import uuid
from collections.abc import AsyncGenerator, Generator
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.core.db import get_db
from app.features.base.crud import RecordNotFoundError
from app.features.user.crud.address import crud_address
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


def test_get_user_addresses_not_owned_returns_error_payload(
    client: TestClient,
) -> None:
    owner_user_id = uuid.uuid4()

    response = client.get(f"/api/v1/address/users/{owner_user_id}/addresses")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "address.not_found",
            "message": "Adresse introuvable",
            "details": {"user_id": str(owner_user_id)},
        }
    }


def test_get_user_address_not_found_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    current_user: SimpleNamespace,
) -> None:
    address_id = uuid.uuid4()

    monkeypatch.setattr(
        crud_address,
        "read",
        AsyncMock(side_effect=RecordNotFoundError("address missing")),
    )

    response = client.get(
        f"/api/v1/address/users/{current_user.id}/addresses/{address_id}"
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "address.not_found",
            "message": f"Address '{address_id}' not found",
            "details": {"address_id": str(address_id)},
        }
    }


def test_get_user_address_mismatched_owner_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    current_user: SimpleNamespace,
) -> None:
    address_id = uuid.uuid4()

    monkeypatch.setattr(
        crud_address,
        "read",
        AsyncMock(return_value=SimpleNamespace(user_id=uuid.uuid4())),
    )

    response = client.get(
        f"/api/v1/address/users/{current_user.id}/addresses/{address_id}"
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "address.not_found",
            "message": f"Address '{address_id}' not found",
            "details": {"address_id": str(address_id)},
        }
    }


def test_get_user_addresses_by_type_invalid_returns_error_payload(
    client: TestClient,
    current_user: SimpleNamespace,
) -> None:
    response = client.get(
        f"/api/v1/address/users/{current_user.id}/addresses/by-type/invalid"
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "address.type.invalid",
            "message": "Invalid address type. Must be one of: billing, other, shipping",
            "details": {
                "address_type": "invalid",
                "allowed": ["billing", "other", "shipping"],
            },
        }
    }
