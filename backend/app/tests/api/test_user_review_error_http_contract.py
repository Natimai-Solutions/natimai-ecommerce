import uuid
from collections.abc import AsyncGenerator, Generator
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.core.db import get_db
from app.features.base.crud import RecordNotFoundError
from app.features.user.crud.review import crud_review
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


def test_get_user_reviews_not_owned_returns_error_payload(client: TestClient) -> None:
    owner_user_id = uuid.uuid4()

    response = client.get(f"/api/v1/review/users/{owner_user_id}/reviews")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "review.not_found",
            "message": "Avis introuvable",
            "details": {"user_id": str(owner_user_id)},
        }
    }


def test_get_user_review_not_found_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    current_user: SimpleNamespace,
) -> None:
    review_id = uuid.uuid4()

    monkeypatch.setattr(
        crud_review,
        "read",
        AsyncMock(side_effect=RecordNotFoundError("review missing")),
    )

    response = client.get(f"/api/v1/review/users/{current_user.id}/reviews/{review_id}")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "review.not_found",
            "message": f"Review '{review_id}' not found",
            "details": {"review_id": str(review_id)},
        }
    }


def test_create_user_review_already_exists_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    current_user: SimpleNamespace,
) -> None:
    product_id = uuid.uuid4()

    monkeypatch.setattr(
        crud_review,
        "get_by_user_and_product",
        AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4())),
    )

    response = client.post(
        f"/api/v1/review/users/{current_user.id}/reviews",
        json={
            "rating": 5,
            "comment": "great",
            "product_id": str(product_id),
            "user_id": str(current_user.id),
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "review.already_exists",
            "message": "User already has a review for this product",
            "details": {
                "user_id": str(current_user.id),
                "product_id": str(product_id),
            },
        }
    }


def test_get_user_review_for_product_not_found_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    current_user: SimpleNamespace,
) -> None:
    product_id = uuid.uuid4()

    monkeypatch.setattr(
        crud_review,
        "get_by_user_and_product",
        AsyncMock(return_value=None),
    )

    response = client.get(
        f"/api/v1/review/products/{product_id}/reviews/user/{current_user.id}"
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "review.not_found",
            "message": "Review not found for this user and product",
            "details": {
                "user_id": str(current_user.id),
                "product_id": str(product_id),
            },
        }
    }
