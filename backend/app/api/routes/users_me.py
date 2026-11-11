"""Customer profile endpoints: read and edit one's own identity, change password.

The storefront « Mon compte → Profil » tab relies on these. The e-mail is
shown but not editable here: changing it must prove ownership of the new
address first (a verification flow that does not exist yet).

R8 / U8 adds the customer's data rights in self-service: a JSON export of
everything the shop holds (``GET /users/me/export``) and the erasure of the
account (``POST /users/me/delete``), see ``features/user/services/privacy``.
"""

from __future__ import annotations

import datetime
import json
import uuid

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlmodel import col, select

from app.api.deps import CurrentUser, CurrentUserEnrolling, SessionDep
from app.core.auth_cookies import clear_refresh_cookie
from app.core.config import settings
from app.core.errors import AppError
from app.core.rate_limit import get_client_ip, hit_rate_limit
from app.core.security import (
    aget_password_hash,
    averify_password,
    new_security_stamp,
)
from app.features.system import audit
from app.features.user.crud.refresh_token import crud_user_refresh_token
from app.features.user.models.oauth_link import UserOAuthLink
from app.features.user.services.privacy import erase_account, export_account

router = APIRouter(prefix="/users/me", tags=["user"])


class MyProfilePublic(BaseModel):
    """What the customer sees of their own account."""

    id: uuid.UUID
    email: str
    full_name: str | None = None
    phone: str | None = None
    is_verified: bool = False
    #: Opened at checkout without a password: the storefront offers to finish it.
    is_guest: bool = False
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


class MyAccountDeletion(BaseModel):
    """Erase my account: the e-mail typed back, and the password when the
    account has one (an account opened with Google / Microsoft only may
    leave it empty)."""

    confirmation: str = Field(min_length=1, max_length=255)
    password: str | None = Field(default=None, max_length=128)


def _profile_of(user: CurrentUser) -> MyProfilePublic:
    return MyProfilePublic(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        phone=user.phone,
        is_verified=bool(user.is_verified),
        is_guest=bool(user.is_guest),
        created_at=getattr(user, "created_at", None),
    )


@router.get("", response_model=MyProfilePublic, summary="My profile")
async def get_my_profile(current_user: CurrentUserEnrolling) -> MyProfilePublic:
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
    if not current_user.hashed_password or not await averify_password(
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
    current_user.hashed_password = await aget_password_hash(payload.new_password)
    current_user.security_stamp = new_security_stamp()
    session.add(current_user)
    await crud_user_refresh_token.revoke_all_active_for_user(
        session=session, user_id=current_user.id, reason="password_change"
    )
    await session.commit()


@router.get(
    "/export",
    summary="Export my data (JSON)",
    response_class=Response,
    responses={200: {"content": {"application/json": {}}}},
)
async def export_my_data(session: SessionDep, current_user: CurrentUser) -> Response:
    """Download everything the shop holds about me, as a JSON file (R8 / U8).

    Five exports an hour per account: the file is cheap to build but it is
    the whole history, and a leaked session must not drain it in a loop.
    """
    if await hit_rate_limit(
        f"account-export:user:{current_user.id}", limit=5, window_seconds=3600
    ):
        raise AppError(
            code="account.export.rate_limited",
            status_code=429,
            message="Trop d'exports : réessayez dans une heure.",
        )
    payload = await export_account(session, current_user)
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")
    return Response(
        content=json.dumps(payload, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="mes-donnees-{stamp}.json"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/delete", status_code=204, summary="Erase my account")
async def delete_my_account(
    payload: MyAccountDeletion,
    request: Request,
    response: Response,
    session: SessionDep,
    current_user: CurrentUser,
) -> None:
    """Erase my personal data and close the account (R8 / U8).

    The e-mail typed back guards against a stray click; the password proves
    the person at the keyboard is the account holder (not required for an
    account that only ever signed in through Google / Microsoft). Orders,
    invoices and payments stay for the legal retention period, detached from
    any name, e-mail or phone; an order still in progress blocks the erasure.
    """
    if await hit_rate_limit(
        f"account-delete:user:{current_user.id}",
        limit=settings.LOGIN_RATE_LIMIT_ATTEMPTS,
        window_seconds=settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS,
    ):
        raise AppError(
            code="account.delete.rate_limited",
            status_code=429,
            message="Trop de tentatives. Réessayez dans quelques minutes.",
        )
    if payload.confirmation.strip().lower() != current_user.email.lower():
        raise AppError(
            code="account.delete.confirmation_mismatch",
            status_code=400,
            message="Saisissez l'adresse e-mail du compte pour confirmer.",
            details={"field": "confirmation"},
        )
    has_provider = (
        await session.exec(
            select(UserOAuthLink.id).where(
                col(UserOAuthLink.user_id) == current_user.id
            )
        )
    ).first() is not None
    if payload.password or not has_provider:
        if not payload.password or not await averify_password(
            payload.password, current_user.hashed_password or ""
        ):
            raise AppError(
                code="user.password.invalid_current",
                status_code=400,
                message="Le mot de passe actuel est incorrect.",
                details={"field": "password"},
            )
    user_id = current_user.id
    await erase_account(session, current_user)
    clear_refresh_cookie(response)
    await audit.record(
        event="account.deleted",
        actor_id=user_id,
        method="POST",
        path=str(request.url.path),
        status_code=204,
        ip=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details={"reason": "customer_request"},
        session=session,
    )
