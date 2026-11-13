import datetime
import secrets
import uuid
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.security import averify_password, get_password_hash
from app.features.base.crud import CrudBase
from app.features.user.models.user import User, UserCreate, UserUpdate

# Lazily-built dummy hash used to equalize the timing of failed logins on
# unknown emails (see CrudUser.authenticate). Computed once per process.
_dummy_password_hash: str | None = None


def _get_dummy_password_hash() -> str:
    """Return a process-wide dummy bcrypt hash for timing equalization."""
    global _dummy_password_hash
    if _dummy_password_hash is None:
        _dummy_password_hash = get_password_hash(secrets.token_urlsafe(16))
    return _dummy_password_hash


class AccountLockedError(Exception):
    """Raised when authentication is attempted on a temporarily locked account."""

    def __init__(self, locked_until: datetime.datetime) -> None:
        self.locked_until = locked_until
        super().__init__(f"Account locked until {locked_until.isoformat()}")


def _utcnow() -> datetime.datetime:
    """Aware UTC now — the DB columns are TIMESTAMP WITH TIME ZONE."""
    return datetime.datetime.now(datetime.UTC)


def _pair_keys(user_id: uuid.UUID, client_ip: str | None) -> tuple[str, str]:
    pair = f"{user_id}:{client_ip or 'unknown'}"
    return f"login:fail:{pair}", f"login:lock:{pair}"


async def _redis_call(operation: Any) -> Any:
    """Run a Redis call; fail closed (503) like the login throttle."""
    from app.core.errors import AppError

    try:
        return await operation
    except Exception as exc:  # noqa: BLE001 — any Redis failure closes the login
        raise AppError(
            code="rate_limit.unavailable",
            status_code=503,
            message="Service momentanément indisponible : réessayez dans un instant.",
            details={},
        ) from exc


async def _pair_locked_until(
    user_id: uuid.UUID, client_ip: str | None
) -> datetime.datetime | None:
    """When this address may try this account again, if it is locked out."""
    from app.core.rate_limit import shared_redis

    _, lock_key = _pair_keys(user_id, client_ip)
    ttl = await _redis_call(shared_redis().ttl(lock_key))
    if ttl is None or int(ttl) <= 0:
        return None
    return _utcnow() + datetime.timedelta(seconds=int(ttl))


async def _count_pair_failure(
    user_id: uuid.UUID, client_ip: str | None
) -> datetime.datetime | None:
    """Count a failure from this address; returns the lock end once it locks."""
    from app.core.rate_limit import shared_redis

    fail_key, lock_key = _pair_keys(user_id, client_ip)
    window = settings.LOGIN_LOCKOUT_MINUTES * 60
    redis = shared_redis()

    async def _incr() -> Any:
        async with redis.pipeline(transaction=True) as pipe:
            pipe.incr(fail_key)
            pipe.expire(fail_key, window, nx=True)
            return await pipe.execute()

    count, _ = await _redis_call(_incr())
    if int(count) < settings.LOGIN_LOCKOUT_MAX_FAILURES:
        return None

    async def _lock() -> Any:
        async with redis.pipeline(transaction=True) as pipe:
            pipe.set(lock_key, "1", ex=window)
            pipe.delete(fail_key)
            return await pipe.execute()

    await _redis_call(_lock())
    return _utcnow() + datetime.timedelta(seconds=window)


async def _clear_pair(user_id: uuid.UUID, client_ip: str | None) -> None:
    from app.core.rate_limit import shared_redis

    await _redis_call(shared_redis().delete(*_pair_keys(user_id, client_ip)))


def mark_logged_in(user: User) -> None:
    """Horodater une connexion réussie (mot de passe, OAuth, inscription).

    Ne commit pas : l'appelant enchaîne sur l'émission du refresh token, dont
    la création commit déjà. ``last_login`` existait en colonne sans jamais
    être écrit ; le back-office (A15) s'appuie dessus pour savoir si un compte
    invité a été ouvert.
    """
    user.last_login = _utcnow()


class CrudUser(CrudBase[User, UserCreate, UserUpdate]):
    """Represents crud user."""

    async def create(
        self,
        session: AsyncSession,
        *,
        data: UserCreate,
        user: User | None,
    ) -> User:
        """
        Create new user with automatic password hashing.

        The UserCreate model automatically converts 'password' to 'hashed_password'.
        """
        return await super().create(session, data=data, user=user)

    async def update(
        self,
        session: AsyncSession,
        *,
        id: uuid.UUID,
        data: UserUpdate | dict[str, Any],
        user: User | None = None,
        record: User | None = None,
    ) -> User:
        """
        Update user with automatic password hashing if password is provided.

        The UserUpdate model automatically converts 'password' to 'hashed_password'.
        """
        return await super().update(
            session,
            id=id,
            data=data,
            user=user,
            record=record,
        )

    async def authenticate(
        self,
        session: AsyncSession,
        *,
        email: str,
        password: str,
        client_ip: str | None = None,
    ) -> User | None:
        """Authenticate user by email and password, with lockout.

        After ``LOGIN_LOCKOUT_MAX_FAILURES`` wrong passwords from one address,
        that address is locked out of the account for
        ``LOGIN_LOCKOUT_MINUTES`` — the owner, from elsewhere, still signs in
        (audit 2026-11, S11). ``LOGIN_ACCOUNT_LOCKOUT_MAX_FAILURES``
        consecutive failures from anywhere lock the account itself (a
        password reset lifts it). A successful login resets both counters.

        Raises:
            AccountLockedError: while the lock is active (also on a correct
                password — otherwise the lock would leak password validity).
        """
        stmt = select(User).where(User.email == email)
        result = await session.exec(stmt)
        user = result.first()

        if not user:
            # Timing equalization: run a bcrypt verify for unknown emails too,
            # so the response time does not reveal whether the account exists.
            await averify_password(password, _get_dummy_password_hash())
            return None

        now = _utcnow()
        pair_until = await _pair_locked_until(user.id, client_ip)
        if pair_until is not None:
            raise AccountLockedError(pair_until)
        if user.locked_until is not None and user.locked_until > now:
            raise AccountLockedError(user.locked_until)

        if not await averify_password(password, user.hashed_password):
            await self.register_failed_attempt(session, user, client_ip=client_ip)
            return None

        # Successful login: clear any stale counter/expired lock. The commit
        # expires the instance, so refresh before handing it to the caller
        # (post-commit attribute reads would MissingGreenlet).
        await _clear_pair(user.id, client_ip)
        if user.failed_login_attempts or user.locked_until is not None:
            user.failed_login_attempts = 0
            user.locked_until = None
            session.add(user)
            await session.commit()
            await session.refresh(user)
        return user

    async def register_failed_attempt(
        self, session: AsyncSession, user: User, *, client_ip: str | None = None
    ) -> None:
        """Count a failed sign-in (wrong second factor too) towards the lockouts:
        the address's on this account, and the account-wide guard.

        Raises :class:`AccountLockedError` when this failure locks either.
        """
        now = _utcnow()
        user_id = user.id
        user.failed_login_attempts += 1
        locked_until: datetime.datetime | None = None
        if user.failed_login_attempts >= settings.LOGIN_ACCOUNT_LOCKOUT_MAX_FAILURES:
            locked_until = now + datetime.timedelta(
                minutes=settings.LOGIN_LOCKOUT_MINUTES
            )
            user.locked_until = locked_until
            user.failed_login_attempts = 0
        session.add(user)
        await session.commit()
        pair_until = await _count_pair_failure(user_id, client_ip)
        until = locked_until or pair_until
        if until is not None:
            raise AccountLockedError(until)

    async def get_by_email(self, session: AsyncSession, *, email: str) -> User | None:
        """
        Get user by email address.
        """
        stmt = select(User).where(User.email == email)
        result = await session.exec(stmt)
        return result.first()

    async def is_active(self, user: User) -> bool:
        """
        Check if user is active.
        """
        return user.is_active

    async def is_superuser(self, user: User) -> bool:
        """
        Check if user is superuser.
        """
        return user.is_superuser


crud_user = CrudUser(
    model=User,
    schema_create=UserCreate,
    schema_update=UserUpdate,
    order_by=User.id,
)
