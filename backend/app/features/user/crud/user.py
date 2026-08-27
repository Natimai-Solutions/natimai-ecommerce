import datetime
import secrets
import uuid
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.security import get_password_hash, verify_password
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


def _utcnow_naive() -> datetime.datetime:
    """Naive UTC now — the DB columns are TIMESTAMP WITHOUT TIME ZONE."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


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
        self, session: AsyncSession, *, email: str, password: str
    ) -> User | None:
        """Authenticate user by email and password, with account lockout.

        After ``LOGIN_LOCKOUT_MAX_FAILURES`` consecutive wrong passwords the
        account is locked for ``LOGIN_LOCKOUT_MINUTES`` (brute-force guard);
        a successful login resets the counter.

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
            verify_password(password, _get_dummy_password_hash())
            return None

        now = _utcnow_naive()
        if user.locked_until is not None and user.locked_until > now:
            raise AccountLockedError(user.locked_until)

        if not verify_password(password, user.hashed_password):
            user.failed_login_attempts += 1
            locked_until: datetime.datetime | None = None
            if user.failed_login_attempts >= settings.LOGIN_LOCKOUT_MAX_FAILURES:
                locked_until = now + datetime.timedelta(
                    minutes=settings.LOGIN_LOCKOUT_MINUTES
                )
                user.locked_until = locked_until
                user.failed_login_attempts = 0
            session.add(user)
            await session.commit()
            if locked_until is not None:
                raise AccountLockedError(locked_until)
            return None

        # Successful login: clear any stale counter/expired lock. The commit
        # expires the instance, so refresh before handing it to the caller
        # (post-commit attribute reads would MissingGreenlet).
        if user.failed_login_attempts or user.locked_until is not None:
            user.failed_login_attempts = 0
            user.locked_until = None
            session.add(user)
            await session.commit()
            await session.refresh(user)
        return user

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
