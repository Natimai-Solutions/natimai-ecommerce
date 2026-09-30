"""Customer profile endpoints: read and edit one's own identity, change password.

The storefront « Mon compte → Profil » tab relies on these. The e-mail is
shown but not editable here: changing it must prove ownership of the new
address first (a verification flow that does not exist yet).
"""

from __future__ import annotations

import datetime
import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from app.api.deps import CurrentUser, SessionDep
from app.core.config import settings
from app.core.errors import AppError
from app.core.rate_limit import hit_rate_limit
from app.core.security import get_password_hash, verify_password
from app.features.user.crud.refresh_token import crud_user_refresh_token

router = APIRouter(prefix="/users/me", tags=["user"])


class MyProfilePublic(BaseModel):
    """What the customer sees of their own account."""

    id: uuid.UUID
    email: str
    full_name: str | None = None
    phone: str | None = None
    is_verified: bool = False
    created_at: datetime.datetime | None = None


class MyProfileUpdate(BaseModel):
    """Editable identity fields. An empty string clears the field."""

    full_name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=50)

    @field_validator("full_name", "phone")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()


class MyPasswordChange(BaseModel):
    """Change the password while signed in: the current one is required."""

    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


def _profile_of(user: CurrentUser) -> MyProfilePublic:
    return MyProfilePublic(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        phone=user.phone,
        is_verified=bool(user.is_verified),
        created_at=getattr(user, "created_at", None),
    )


@router.get("", response_model=MyProfilePublic, summary="My profile")
async def get_my_profile(current_user: CurrentUser) -> MyProfilePublic:
    """Identity of the signed-in customer."""
    return _profile_of(current_user)


@router.patch("", response_model=MyProfilePublic, summary="Edit my profile")
async def update_my_profile(
    payload: MyProfileUpdate, session: SessionDep, current_user: CurrentUser
) -> MyProfilePublic:
    """Update the name and phone number. Fields left out are unchanged."""
    changed = payload.model_dump(exclude_unset=True)
    for field, value in changed.items():
        setattr(current_user, field, value or None)
    if changed:
        session.add(current_user)
        await session.commit()
        await session.refresh(current_user)
    return _profile_of(current_user)


@router.post("/password", status_code=204, summary="Change my password")
async def change_my_password(
    payload: MyPasswordChange,
    session: SessionDep,
    current_user: CurrentUser,
) -> None:
    """Replace the password after checking the current one.

    Every open session is closed afterwards, the current one included: the
    customer signs in again with the new password. An account created through
    Google / Microsoft has no password it knows of; « mot de passe oublié »
    sets one.
    """
    if await hit_rate_limit(
        f"password-change:user:{current_user.id}",
        limit=settings.LOGIN_RATE_LIMIT_ATTEMPTS,
        window_seconds=settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS,
    ):
        raise AppError(
            code="user.password.rate_limited",
            status_code=429,
            message="Trop de tentatives. Réessayez dans quelques minutes.",
        )
    if not current_user.hashed_password or not verify_password(
        payload.current_password, current_user.hashed_password
    ):
        raise AppError(
            code="user.password.invalid_current",
            status_code=400,
            message="Le mot de passe actuel est incorrect.",
            details={"field": "current_password"},
        )
    if payload.new_password == payload.current_password:
        raise AppError(
            code="user.password.unchanged",
            status_code=400,
            message="Le nouveau mot de passe doit être différent de l'actuel.",
            details={"field": "new_password"},
        )
    current_user.hashed_password = get_password_hash(payload.new_password)
    session.add(current_user)
    await crud_user_refresh_token.revoke_all_active_for_user(
        session=session, user_id=current_user.id, reason="password_change"
    )
    await session.commit()
