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

    # A freshly migrated database has no user, and the fixture used to assert
    # its way out of that — the test then errored on any clean checkout instead
    # of running. It creates its own user in that case, and removes it
    # afterwards so the run leaves no trace.
    created_user_id: uuid.UUID | None = None
    if user is None:
        user = User(
            email=f"postal-codes-test-{uuid.uuid4().hex[:8]}@example.invalid",
            hashed_password="not-a-usable-hash",
            is_active=True,
            is_superuser=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        created_user_id = user.id

    user_id = user.id  # capture before rollback — the instance expires with it
    # End the read transaction: the session-scoped ``db`` fixture would
    # otherwise sit idle-in-transaction for the rest of the run, and its
    # lock on ``users`` blocks the integration suite's DROP SCHEMA.
    await db.rollback()
    stub = SimpleNamespace(id=user_id, is_superuser=True, is_active=True)

    async def _override() -> SimpleNamespace:
        return stub

    app.dependency_overrides[get_current_user_optional] = _override
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_current_user_optional, None)
        if created_user_id is not None:
            # Only the row this fixture created — never a real dev user.
            to_delete = await db.get(User, created_user_id)
            if to_delete is not None:
                await db.delete(to_delete)
                await db.commit()


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
