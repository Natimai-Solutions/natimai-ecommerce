import uuid
from collections.abc import AsyncGenerator, Generator
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.core.db import get_db
from app.features.user.crud.wishlist import crud_wishlist, crud_wishlist_item
from app.main import app


@pytest.fixture
def current_user() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), is_superuser=False, is_active=True)


@pytest.fixture
def db_session() -> SimpleNamespace:
    return SimpleNamespace(get=AsyncMock(return_value=None))


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


def test_get_user_wishlists_not_owned_returns_error_payload(
    client: TestClient,
) -> None:
    owner_user_id = uuid.uuid4()

    response = client.get(f"/api/v1/wishlist/users/{owner_user_id}/wishlists")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "wishlist.not_found",
            "message": "Liste introuvable",
            "details": {"user_id": str(owner_user_id)},
        }
    }


def test_get_user_wishlist_not_found_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    current_user: SimpleNamespace,
) -> None:
    wishlist_id = uuid.uuid4()

    monkeypatch.setattr(
        crud_wishlist,
        "get_user_wishlist_by_id",
        AsyncMock(return_value=None),
    )

    response = client.get(
        f"/api/v1/wishlist/users/{current_user.id}/wishlists/{wishlist_id}"
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "wishlist.not_found",
            "message": f"Wishlist '{wishlist_id}' not found",
            "details": {"wishlist_id": str(wishlist_id)},
        }
    }


def test_add_product_to_my_wishlist_product_not_found_returns_error_payload(
    client: TestClient,
) -> None:
    product_id = uuid.uuid4()

    response = client.post(
        "/api/v1/wishlist/me/items",
        json={"product_id": str(product_id), "notes": "gift"},
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "wishlist.product.not_found",
            "message": f"Product '{product_id}' not found",
            "details": {"product_id": str(product_id)},
        }
    }


def test_remove_product_from_my_wishlist_missing_item_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    current_user: SimpleNamespace,
) -> None:
    wishlist_id = uuid.uuid4()
    product_id = uuid.uuid4()

    monkeypatch.setattr(
        crud_wishlist,
        "get_or_create_default_for_user",
        AsyncMock(
            return_value=SimpleNamespace(id=wishlist_id, user_id=current_user.id)
        ),
    )
    monkeypatch.setattr(
        crud_wishlist_item,
        "deactivate_by_wishlist_and_product",
        AsyncMock(return_value=False),
    )

    response = client.delete(f"/api/v1/wishlist/me/items/{product_id}")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "wishlist.product.not_in_wishlist",
            "message": f"Product '{product_id}' not found in wishlist",
            "details": {
                "product_id": str(product_id),
                "wishlist_id": str(wishlist_id),
            },
        }
    }
