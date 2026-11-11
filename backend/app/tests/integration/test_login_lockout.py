"""Integration tests: per-account lockout on repeated failed logins.

Real DB session and Redis — the per-address lockout lives in Redis, the
account-wide guard mutates ``failed_login_attempts``/``locked_until``
and commits, so a mocked session would not exercise the actual behaviour
(including the post-commit refresh that guards against MissingGreenlet).
"""

import datetime
import uuid

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
async def test_an_address_is_locked_out_not_the_account(
    db_session: AsyncSession,
) -> None:
    """Audit 2026-11, S11: five wrong passwords locked the account itself, so
    anyone could lock any account (an administrator's included) from one
    address, again and again. Only that address is locked out now."""
    _user, email = await _make_user(db_session, f"lockout+{uuid.uuid4().hex[:6]}@t.l")
    attacker, owner = "198.51.100.7", "203.0.113.9"
    max_failures = settings.LOGIN_LOCKOUT_MAX_FAILURES

    for _ in range(max_failures - 1):
        assert (
            await crud_user.authenticate(
                session=db_session, email=email, password="wrong", client_ip=attacker
            )
            is None
        )
    # The Nth failure locks this address out of the account…
    with pytest.raises(AccountLockedError):
        await crud_user.authenticate(
            session=db_session, email=email, password="wrong", client_ip=attacker
        )
    # …even with the right password (no validity leak)…
    with pytest.raises(AccountLockedError):
        await crud_user.authenticate(
            session=db_session, email=email, password=_PASSWORD, client_ip=attacker
        )
    # …while the owner, from their own address, signs in.
    authenticated = await crud_user.authenticate(
        session=db_session, email=email, password=_PASSWORD, client_ip=owner
    )
    assert authenticated is not None
    assert authenticated.failed_login_attempts == 0


@pytest.mark.asyncio
async def test_a_distributed_brute_force_locks_the_account(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Many addresses, few tries each: the account-wide guard locks the
    account (a password reset lifts it)."""
    monkeypatch.setattr(settings, "LOGIN_ACCOUNT_LOCKOUT_MAX_FAILURES", 3)
    user, email = await _make_user(db_session, f"spread+{uuid.uuid4().hex[:6]}@t.l")
    user_id = user.id
    for n in range(2):
        assert (
            await crud_user.authenticate(
                session=db_session,
                email=email,
                password="wrong",
                client_ip=f"192.0.2.{n}",
            )
            is None
        )
    with pytest.raises(AccountLockedError):
        await crud_user.authenticate(
            session=db_session, email=email, password="wrong", client_ip="192.0.2.9"
        )
    with pytest.raises(AccountLockedError):
        await crud_user.authenticate(
            session=db_session, email=email, password=_PASSWORD, client_ip="203.0.113.1"
        )

    # The lock expires (or a password reset clears it): the owner is back.
    refreshed = await db_session.get(User, user_id)
    assert refreshed is not None
    refreshed.locked_until = datetime.datetime.now(datetime.UTC) - datetime.timedelta(
        minutes=1
    )
    db_session.add(refreshed)
    await db_session.flush()
    authenticated = await crud_user.authenticate(
        session=db_session, email=email, password=_PASSWORD, client_ip="203.0.113.1"
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
