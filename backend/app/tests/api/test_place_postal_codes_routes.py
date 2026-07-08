"""End-to-end contract tests for the place postal-codes routes.

These hit the real app + database (no mocked session) on purpose: the
PUT handler once crashed with MissingGreenlet by reading ORM attributes
after ``session.commit()`` — a class of bug mocked-session tests can't see.

Auth is dependency-overridden (the login fixtures are unusable against a dev
database whose superuser password differs from settings), but it points to a
REAL user row so ``created_by_id`` foreign keys stay valid.
"""

import uuid
from collections.abc import AsyncGenerator
from types import SimpleNamespace

import pytest_asyncio
from fastapi.testclient import TestClient
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import get_current_user_optional
from app.features.user.models.user import User
from app.main import app

_BASE = "/api/v1/place"


def _unique_code() -> str:
    # Unique pseudo postal codes so reruns never trip the (country, code)
    # unique constraint, whatever state the dev database is in.
    return f"98{uuid.uuid4().hex[:8]}"


@pytest_asyncio.fixture
async def real_user_auth(db: AsyncSession) -> AsyncGenerator[None, None]:
    result = await db.exec(select(User).where(col(User.is_active).is_(True)).limit(1))
    user = result.first()
    assert user is not None, "dev database has no user to authenticate as"
    stub = SimpleNamespace(id=user.id, is_superuser=True, is_active=True)

    async def _override() -> SimpleNamespace:
        return stub

    app.dependency_overrides[get_current_user_optional] = _override
    yield
    app.dependency_overrides.pop(get_current_user_optional, None)


def test_put_then_get_postal_codes_roundtrip(
    client: TestClient,
    real_user_auth: None,
) -> None:
    # Fixture is used for its dependency-override side effects.
    assert real_user_auth is None
    created = client.post(
        f"{_BASE}/",
        json={
            "name": f"Île test {uuid.uuid4().hex[:6]}",
            "type": "island",
            "country": "PF",
        },
    )
    assert created.status_code == 200, created.text
    place_id = created.json()["id"]

    codes = sorted([_unique_code(), _unique_code()])
    try:
        # Regression guard: this PUT used to 500 (MissingGreenlet) because the
        # handler read row.postal_code after the commit.
        response = client.put(
            f"{_BASE}/{place_id}/postal-codes",
            json={"country": "PF", "postal_codes": codes},
        )
        assert response.status_code == 200, response.text
        assert sorted(response.json()) == codes

        listed = client.get(f"{_BASE}/{place_id}/postal-codes")
        assert listed.status_code == 200
        assert sorted(listed.json()) == codes

        resolved = client.get(
            f"{_BASE}/geo/resolve-postal",
            params={"country": "PF", "postal_code": codes[0]},
        )
        assert resolved.status_code == 200
        assert resolved.json()["place"]["id"] == place_id
    finally:
        # Detach the codes then remove the test place.
        client.put(
            f"{_BASE}/{place_id}/postal-codes",
            json={"country": "PF", "postal_codes": []},
        )
        client.delete(f"{_BASE}/{place_id}")
