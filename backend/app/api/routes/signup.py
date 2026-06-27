"""Email-OTP self-service signup.

Flow (OAuth signup is handled separately by the OAuth callback):
    POST /signup/send-otp   → email a 6-digit code (rate-limited)
    POST /signup/verify-otp → validate the code, return a single-use signup_token
    POST /signup/complete   → create the account, log the user in (refresh cookie)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Response
from pydantic import BaseModel, EmailStr, Field

from app.api.deps import RedisDep, SessionDep
from app.api.routes.login import _build_token_bundle
from app.core.auth_cookies import set_refresh_cookie
from app.core.config import settings
from app.core.errors import AppError
from app.core.security import get_password_hash
from app.features.notification.providers import (
    NotificationMessage,
    UnknownNotificationProviderError,
    get_notification_provider,
)
from app.features.user.crud.refresh_token import crud_user_refresh_token
from app.features.user.crud.user import crud_user
from app.features.user.models.user import AccessTokenResponse, User
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


def _render_otp_email(code: str) -> tuple[str, str]:
    shop = getattr(settings, "SHOP_NAME", "Natimai")
    text = (
        f"Bonjour,\n\n"
        f"Votre code de vérification {shop} est : {code}\n\n"
        f"Il est valable {OTP_VALID_MINUTES} minutes. Si vous n'êtes pas à "
        f"l'origine de cette demande, ignorez cet email.\n\n"
        f"L'équipe {shop}\n"
    )
    html = f"""\
<!DOCTYPE html>
<html lang="fr"><head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif;background:#f5f5f5;margin:0;padding:0;">
  <div style="max-width:480px;margin:32px auto;background:#fff;border-radius:8px;overflow:hidden;">
    <div style="background:#1a3c5e;padding:24px 32px;"><h1 style="color:#fff;margin:0;font-size:20px;">Vérification de votre email</h1></div>
    <div style="padding:32px;color:#333;">
      <p>Bonjour,</p>
      <p>Votre code de vérification est :</p>
      <p style="font-size:32px;font-weight:bold;letter-spacing:8px;text-align:center;background:#f0f4f8;border-radius:6px;padding:16px 0;">{code}</p>
      <p>Il est valable <strong>{OTP_VALID_MINUTES} minutes</strong>. Si vous n'êtes pas à l'origine de cette demande, ignorez cet email.</p>
      <p>L'équipe {shop}</p>
    </div>
  </div>
</body></html>
"""
    return text, html


async def _send_otp_email(email: str, code: str) -> None:
    text, html = _render_otp_email(code)
    try:
        provider = get_notification_provider(
            settings.PAYMENT_NOTIFICATIONS_EMAIL_PROVIDER
        )
    except UnknownNotificationProviderError:
        provider = get_notification_provider("noop")

    shop = getattr(settings, "SHOP_NAME", "Natimai")
    result = await provider.send(
        NotificationMessage(
            channel="email",
            recipient=email,
            subject=f"{shop} — votre code de vérification",
            text=text,
            html=html,
            metadata={"event_type": "signup.otp"},
        )
    )
    if not result.delivered:
        logger.warning("signup OTP email not delivered to %s: %s", email, result.error)
    # Local dev affordance: surface the code in logs when no real mailer is set up.
    if settings.ENVIRONMENT == "local":
        logger.info("[DEV] signup OTP for %s = %s", email, code)


@router.post("/send-otp", response_model=OkMessage)
async def send_otp(
    body: SendOtpRequest, session: SessionDep, redis: RedisDep
) -> OkMessage:
    """Email a verification code (refuses if the address already has an account)."""
    existing = await crud_user.get_by_email(session, email=str(body.email))
    if existing is not None:
        raise AppError(
            code="signup.email_exists",
            status_code=400,
            message="Un compte existe déjà avec cet email.",
        )

    code = await create_otp(redis, str(body.email))
    await _send_otp_email(str(body.email), code)
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
    if await crud_user.get_by_email(session, email=email) is not None:
        raise AppError(
            code="signup.email_exists",
            status_code=400,
            message="Un compte existe déjà avec cet email.",
        )

    # Build the row directly: the password-hashing model_validator lives on
    # UserCreate, but the CRUD's model_dump drops the excluded hashed_password —
    # so we hash here and set it on the User explicitly.
    user = User(
        email=email,
        full_name=body.full_name,
        is_verified=True,
        hashed_password=get_password_hash(body.password),
    )
    session.add(user)
    await session.flush()

    user_id = user.id
    access_token, refresh_token, refresh_jti, refresh_expires_at = _build_token_bundle(
        user_id
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
