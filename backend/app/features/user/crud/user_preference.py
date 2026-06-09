import uuid
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.user.models.user_preference import (
    UserPreference,
    UserPreferenceUpdate,
)


async def get_preference_for_user(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
) -> UserPreference | None:
    """Return the preference row for a user, or None if not yet created."""
    stmt = select(UserPreference).where(UserPreference.user_id == user_id)
    result = await session.exec(stmt)
    return result.first()


async def upsert_preference_for_user(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    data: UserPreferenceUpdate,
) -> UserPreference:
    """Create or partially update the preference row for a user.

    Returns the up-to-date preference without committing — the caller commits.
    """
    pref = await get_preference_for_user(session, user_id=user_id)
    # exclude_unset keeps only fields explicitly sent in the request; None clears a value
    updates: dict[str, Any] = data.model_dump(exclude_unset=True)

    if pref is None:
        pref = UserPreference(user_id=user_id, **updates)
    else:
        for field, value in updates.items():
            setattr(pref, field, value)

    session.add(pref)
    return pref
