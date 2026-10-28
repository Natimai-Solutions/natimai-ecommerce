"""Email-OTP self-service signup.

Flow (OAuth signup is handled separately by the OAuth callback):
    POST /signup/send-otp   → email a 6-digit code (rate-limited)
    POST /signup/verify-otp → validate the code, return a single-use signup_token
    POST /signup/complete   → create the account, log the user in (refresh cookie)

Guest checkout (« commande sans compte », see ``services/guest``):
    POST /signup/guest                 → open a passwordless account and its session
    POST /signup/guest/activation-link → e-mail the link that sets its password
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr, Field, field_validator

from app.api.deps import CurrentUser, RedisDep, SessionDep
from app.api.routes.login import _build_token_bundle
from app.core import runtime_settings
from app.core.auth_cookies import set_refresh_cookie
from app.core.captcha import require_captcha
from app.core.config import settings
from app.core.errors import AppError
from app.core.rate_limit import hit_rate_limit, rate_limited
from app.core.security import aget_password_hash
from app.features.notification.email_renderer import render_email
from app.features.notification.mailer import queue_email
from app.features.user.crud.refresh_token import crud_user_refresh_token
from app.features.user.crud.user import crud_user, mark_logged_in
from app.features.user.models.user import AccessTokenResponse, User
from app.features.user.services.guest import (
    claim_guest_account,
    new_guest_user,
    send_guest_activation_link,
)
from app.features.user.services.otp_service import (
    OTP_VALID_MINUTES,
    consume_signup_token,
    create_otp,
    verify_otp,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/signup", tags=["signup"])


class SendOtpRequest(BaseModel):
    """Request an email verification code."""

    email: EmailStr


class VerifyOtpRequest(BaseModel):
    """Validate the emailed code."""

    email: EmailStr
    code: str = Field(..., min_length=4, max_length=10)


class SignupTokenResponse(BaseModel):
    """Single-use token proving the email was verified."""

    signup_token: str


class CompleteSignupRequest(BaseModel):
    """Finalise account creation."""

    signup_token: str
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


class OkMessage(BaseModel):
    """Generic acknowledgement."""

    message: str


class GuestStartRequest(BaseModel):
    """Who orders without an account: enough to deliver and to reach them."""

    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=50)

    @field_validator("full_name", "phone")
    @classmethod
    def strip(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


async def _open_session(
    session: SessionDep, response: Response, user: User
) -> AccessTokenResponse:
    """Sign ``user`` in: refresh cookie set, access token returned. Commits."""
    mark_logged_in(user)
    session.add(user)
    await session.flush()
    user_id = user.id
    access_token, refresh_token, refresh_jti, refresh_expires_at = _build_token_bundle(
        user_id, user.security_stamp
    )
    await crud_user_refresh_token.create_for_user(
        session=session,
        user_id=user_id,
        jti=refresh_jti,
        expires_at=refresh_expires_at,
        user=user,
    )
    set_refresh_cookie(response, refresh_token)
    return AccessTokenResponse(
        access_token=access_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


async def _send_otp_email(session: SessionDep, email: str, code: str) -> None:
    """Queue the sign-up code (sent by the worker, off the request)."""
    rendered = render_email(
        "signup_otp",
        code=code,
        valid_minutes=OTP_VALID_MINUTES,
        shop_name=runtime_settings.peek("shop_name"),
    )
    await queue_email(
        session,
        recipient=email,
        subject=rendered.subject,
        text=rendered.text,
        html=rendered.html,
        event_type="signup.otp",
        resendable=False,  # carries a valid code
    )
    # Local dev affordance: surface the code in logs when no real mailer is set up.
    if settings.ENVIRONMENT == "local":
        logger.info("[DEV] signup OTP for %s = %s", email, code)


@router.post(
    "/send-otp",
    response_model=OkMessage,
    # A public form (R8 / U5): 5 codes per address and 10 minutes — each one
    # is an e-mail sent on the shop's behalf.
    dependencies=[Depends(rate_limited("signup", limit=5, window_seconds=600))],
)
async def send_otp(
    body: SendOtpRequest, request: Request, session: SessionDep, redis: RedisDep
) -> OkMessage:
    """Email a verification code (refuses if the address already has an account)."""
    await require_captcha(request, session)
    existing = await crud_user.get_by_email(session, email=str(body.email))
    # A guest account is taken over by signing up with its address.
    if existing is not None and not existing.is_guest:
        raise AppError(
            code="signup.email_exists",
            status_code=400,
            message="Un compte existe déjà avec cet email.",
        )

    code = await create_otp(redis, str(body.email))
    await _send_otp_email(session, str(body.email), code)
    return OkMessage(message="Un code de vérification a été envoyé par email.")


@router.post("/verify-otp", response_model=SignupTokenResponse)
async def verify_otp_route(
    body: VerifyOtpRequest, redis: RedisDep
) -> SignupTokenResponse:
    """Validate the code and return a single-use signup token."""
    token = await verify_otp(redis, email=str(body.email), code=body.code)
    return SignupTokenResponse(signup_token=token)


@router.post("/complete", response_model=AccessTokenResponse)
async def complete_signup(
    body: CompleteSignupRequest,
    session: SessionDep,
    redis: RedisDep,
    response: Response,
) -> AccessTokenResponse:
    """Create the account (email already verified) and log the user in."""
    email = await consume_signup_token(redis, body.signup_token)

    # Race guard: the email could have been registered between verify and complete.
    existing = await crud_user.get_by_email(session, email=email)
    if existing is not None and not existing.is_guest:
        raise AppError(
            code="signup.email_exists",
            status_code=400,
            message="Un compte existe déjà avec cet email.",
        )

    password_hash = await aget_password_hash(body.password)
    if existing is not None:
        # The code proved the address: the guest account (and its orders)
        # becomes theirs, the sessions opened at checkout are closed.
        user = existing
        await claim_guest_account(session, user)
        user.hashed_password = password_hash
        if body.full_name:
            user.full_name = body.full_name
    else:
        # Build the row directly: the password-hashing model_validator lives on
        # UserCreate, but the CRUD's model_dump drops the excluded
        # hashed_password — so we hash here and set it on the User explicitly.
        user = User(
            email=email,
            full_name=body.full_name,
            is_verified=True,
            hashed_password=password_hash,
        )
    # l'inscription connecte : c'est une première ouverture
    return await _open_session(session, response, user)


@router.post(
    "/guest",
    response_model=AccessTokenResponse,
    # A public form that creates an account: 10 per address and 10 minutes.
    dependencies=[Depends(rate_limited("guest_signup", limit=10, window_seconds=600))],
)
async def start_guest_checkout(
    body: GuestStartRequest,
    request: Request,
    session: SessionDep,
    response: Response,
) -> AccessTokenResponse:
    """Open a passwordless account to order without signing up, and its session.

    An address that already has an account opens nothing (409
    ``signup.guest.account_exists``): ``details.reason`` is ``account`` (sign
    in) or ``guest`` (an earlier guest order: the link to take the account
    over has just been e-mailed).
    """
    await require_captcha(request, session)
    email = str(body.email).strip().lower()
    existing = await crud_user.get_by_email(session, email=email)
    if existing is not None:
        reason = "guest" if existing.is_guest and existing.is_active else "account"
        if reason == "guest" and not await hit_rate_limit(
            f"guest-link:{email}", limit=3, window_seconds=3600
        ):
            await send_guest_activation_link(session, existing)
        raise AppError(
            code="signup.guest.account_exists",
            status_code=409,
            message=(
                "Vous avez déjà commandé avec cette adresse : un lien pour "
                "retrouver votre compte vient de vous être envoyé."
                if reason == "guest"
                else "Un compte existe déjà avec cette adresse : connectez-vous."
            ),
            details={"reason": reason},
        )
    user = new_guest_user(email=email, full_name=body.full_name, phone=body.phone)
    return await _open_session(session, response, user)


@router.post(
    "/guest/activation-link",
    response_model=OkMessage,
    dependencies=[
        Depends(rate_limited("guest_activation", limit=3, window_seconds=600))
    ],
)
async def send_my_guest_activation_link(
    session: SessionDep, current_user: CurrentUser
) -> OkMessage:
    """E-mail the guest the link that sets their password (« créer mon compte »)."""
    if not current_user.is_guest:
        raise AppError(
            code="signup.guest.not_guest",
            status_code=409,
            message="Ce compte a déjà un mot de passe.",
        )
    email = current_user.email
    await send_guest_activation_link(session, current_user)
    return OkMessage(message=f"Un lien vient d'être envoyé à {email}.")
