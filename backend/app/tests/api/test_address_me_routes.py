"""Contract tests for /users/me/addresses self-service endpoints.

Focus on the security hardening: a user can never set ``user_id`` or
``is_validated`` on their own addresses — ownership is derived from the JWT and
validation is admin-only.
"""

import uuid
from collections.abc import AsyncGenerator, Generator
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_active_superuser, get_current_user
from app.core.db import get_db
from app.features.base.crud import RecordNotFoundError
from app.features.user.crud.address import crud_address
from app.features.user.models.address import Address
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


def _address(*, user_id: uuid.UUID, is_validated: bool = False) -> Address:
    return Address(
        street="1 rue des Tests",
        city="Papeete",
        postal_code="98714",
        country="PF",
        type="shipping",
        user_id=user_id,
        is_validated=is_validated,
    )


def test_create_my_address_forces_ownership_and_ignores_injected_fields(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    current_user: SimpleNamespace,
) -> None:
    """A spoofed user_id / is_validated in the body must be discarded."""
    spoofed_user_id = uuid.uuid4()
    created = _address(user_id=current_user.id)
    create_mock = AsyncMock(return_value=created)
    monkeypatch.setattr(crud_address, "create_for_user", create_mock)

    response = client.post(
        "/api/v1/address/users/me/addresses",
        json={
            "street": "1 rue des Tests",
            "city": "Papeete",
            "postal_code": "98714",
            "country": "PF",
            "type": "shipping",
            # malicious extras — must be ignored by AddressMeCreate
            "user_id": str(spoofed_user_id),
            "is_validated": True,
        },
    )

    assert response.status_code == 201
    # Ownership is forced to the authenticated user, never the spoofed id.
    passed_payload = create_mock.call_args.kwargs["data"]
    assert passed_payload.user_id == current_user.id
    assert create_mock.call_args.kwargs["user_id"] == current_user.id
    # The create payload schema has no is_validated field at all.
    assert not hasattr(passed_payload, "is_validated")
    # Response reflects the persisted (non-validated) address.
    assert response.json()["is_validated"] is False
    assert response.json()["user_id"] == str(current_user.id)


def test_update_my_address_cannot_set_is_validated(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    current_user: SimpleNamespace,
) -> None:
    address_id = uuid.uuid4()
    existing = _address(user_id=current_user.id)
    monkeypatch.setattr(crud_address, "read", AsyncMock(return_value=existing))

    update_mock = AsyncMock(return_value=existing)
    monkeypatch.setattr(crud_address, "update", update_mock)

    response = client.patch(
        f"/api/v1/address/users/me/addresses/{address_id}",
        json={"city": "Pirae", "is_validated": True},
    )

    assert response.status_code == 200
    # AddressMeUpdate has no is_validated field, so the payload built for the
    # CRUD layer never carries it.
    update_payload = update_mock.call_args.kwargs["data"]
    assert getattr(update_payload, "is_validated", None) in (None, False)
    assert not update_payload.model_dump(exclude_unset=True).get("is_validated")


def test_get_my_address_mismatched_owner_returns_404(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reading someone else's address is indistinguishable from not-found."""
    foreign = _address(user_id=uuid.uuid4())
    monkeypatch.setattr(crud_address, "read", AsyncMock(return_value=foreign))

    response = client.get(f"/api/v1/address/users/me/addresses/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "address.not_found"


def test_delete_my_address_not_found_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        crud_address,
        "read",
        AsyncMock(side_effect=RecordNotFoundError("address missing")),
    )

    response = client.delete(f"/api/v1/address/users/me/addresses/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "address.not_found"


def test_admin_validate_address_is_idempotent_when_already_validated(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Re-validating an already-validated address must not re-run the mutation."""
    superuser = SimpleNamespace(id=uuid.uuid4(), is_superuser=True, is_active=True)

    async def _override_superuser() -> SimpleNamespace:
        return superuser

    app.dependency_overrides[get_current_active_superuser] = _override_superuser
    try:
        already = _address(user_id=uuid.uuid4(), is_validated=True)
        monkeypatch.setattr(crud_address, "read", AsyncMock(return_value=already))
        validate_mock = AsyncMock()
        monkeypatch.setattr(crud_address, "validate_address", validate_mock)

        response = client.post(
            f"/api/v1/address/admin/addresses/{uuid.uuid4()}/validate"
        )

        assert response.status_code == 200
        assert response.json()["is_validated"] is True
        # Idempotent: no second write when already validated.
        validate_mock.assert_not_awaited()
    finally:
        app.dependency_overrides.pop(get_current_active_superuser, None)


def test_admin_validate_address_validates_pending_address(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    superuser = SimpleNamespace(id=uuid.uuid4(), is_superuser=True, is_active=True)

    async def _override_superuser() -> SimpleNamespace:
        return superuser

    app.dependency_overrides[get_current_active_superuser] = _override_superuser
    try:
        owner_id = uuid.uuid4()
        pending = _address(user_id=owner_id, is_validated=False)
        validated = _address(user_id=owner_id, is_validated=True)
        monkeypatch.setattr(crud_address, "read", AsyncMock(return_value=pending))
        validate_mock = AsyncMock(return_value=validated)
        monkeypatch.setattr(crud_address, "validate_address", validate_mock)

        response = client.post(
            f"/api/v1/address/admin/addresses/{uuid.uuid4()}/validate"
        )

        assert response.status_code == 200
        assert response.json()["is_validated"] is True
        validate_mock.assert_awaited_once()
    finally:
        app.dependency_overrides.pop(get_current_active_superuser, None)
