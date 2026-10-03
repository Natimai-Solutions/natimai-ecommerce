"""Integration tests: per-account lockout on repeated failed logins.

Real DB session — the lockout mutates ``failed_login_attempts``/``locked_until``
and commits, so a mocked session would not exercise the actual behaviour
(including the post-commit refresh that guards against MissingGreenlet).
"""

import datetime

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.security import get_password_hash
from app.features.user.crud.user import AccountLockedError, crud_user
from app.features.user.models.user import User

_PASSWORD = "correct-horse-battery"


async def _make_user(session: AsyncSession, email: str) -> tuple[User, str]:
    """Create a user and return (instance, email as plain str).

    authenticate() commits internally, which expires the instance — tests must
    use the captured string, not ``user.email`` (MissingGreenlet otherwise).
    """
    user = User(
        email=email,
        hashed_password=get_password_hash(_PASSWORD),
        is_active=True,
    )
    session.add(user)
    await session.flush()
    return user, email


@pytest.mark.asyncio
async def test_lockout_after_max_failures_then_reset(
    db_session: AsyncSession,
) -> None:
    user, email = await _make_user(db_session, "lockout@test.local")
    user_id = user.id
    max_failures = settings.LOGIN_LOCKOUT_MAX_FAILURES

    # N-1 wrong passwords: still just "invalid credentials" (None).
    for _ in range(max_failures - 1):
        assert (
            await crud_user.authenticate(
                session=db_session, email=email, password="wrong"
            )
            is None
        )

    # The Nth failure locks the account.
    with pytest.raises(AccountLockedError):
        await crud_user.authenticate(session=db_session, email=email, password="wrong")

    # While locked, even the CORRECT password is rejected (no validity leak).
    with pytest.raises(AccountLockedError):
        await crud_user.authenticate(
            session=db_session, email=email, password=_PASSWORD
        )

    # Expire the lock manually → correct password logs in and resets counters.
    refreshed = await db_session.get(User, user_id)
    assert refreshed is not None
    refreshed.locked_until = datetime.datetime.now(datetime.UTC) - datetime.timedelta(
        minutes=1
    )
    db_session.add(refreshed)
    await db_session.flush()

    authenticated = await crud_user.authenticate(
        session=db_session, email=email, password=_PASSWORD
    )
    assert authenticated is not None
    assert authenticated.failed_login_attempts == 0
    assert authenticated.locked_until is None


@pytest.mark.asyncio
async def test_successful_login_resets_failure_counter(
    db_session: AsyncSession,
) -> None:
    _user, email = await _make_user(db_session, "reset@test.local")

    assert (
        await crud_user.authenticate(session=db_session, email=email, password="wrong")
        is None
    )
    authenticated = await crud_user.authenticate(
        session=db_session, email=email, password=_PASSWORD
    )
    assert authenticated is not None
    assert authenticated.failed_login_attempts == 0

    # Unknown account: no crash, no lockout row created.
    assert (
        await crud_user.authenticate(
            session=db_session, email="ghost@test.local", password="x"
        )
        is None
    )
