"""Two-factor authentication of the administrators (R6).

  GET  /users/me/2fa                 — status
  POST /users/me/2fa/setup           — new secret + QR code (not active yet)
  POST /users/me/2fa/confirm         — first valid code: active, recovery codes
  POST /users/me/2fa/recovery-codes  — new recovery codes (needs a code)
  POST /users/me/2fa/disable         — off (needs the password and a code)

Superusers only, reachable even before enrolment (where it is required, the
rest of the admin is not). Every change is journaled.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.api.deps import CurrentSuperUserEnrolling, SessionDep
from app.core.config import settings
from app.core.errors import AppError
from app.core.rate_limit import get_client_ip
from app.core.security import verify_password
from app.features.system import audit
from app.features.user.models.user import User
from app.features.user.services import two_factor

router = APIRouter(prefix="/users/me/2fa", tags=["user"])


class TwoFactorStatus(BaseModel):
    enabled: bool
    required: bool
    recovery_codes_left: int = 0


class TwoFactorSetup(BaseModel):
    secret: str
    otpauth_uri: str
    qr_svg_data_uri: str


class TwoFactorCode(BaseModel):
    code: str = Field(min_length=6, max_length=20)


class TwoFactorDisable(TwoFactorCode):
    password: str = Field(min_length=1, max_length=200)


class RecoveryCodes(BaseModel):
    recovery_codes: list[str]


def _status(user: User) -> TwoFactorStatus:
    return TwoFactorStatus(
        enabled=bool(user.totp_enabled),
        required=settings.admin_2fa_required,
        recovery_codes_left=two_factor.remaining_recovery_codes(user),
    )


async def _journal(
    request: Request, event: str, user_id: uuid.UUID, email: str
) -> None:
    await audit.record(
        event=event,
        actor_id=user_id,
        actor_email=email,
        ip=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )


@router.get("", response_model=TwoFactorStatus)
async def get_status(current_user: CurrentSuperUserEnrolling) -> TwoFactorStatus:
    return _status(current_user)


@router.post("/setup", response_model=TwoFactorSetup)
async def setup(
    session: SessionDep, current_user: CurrentSuperUserEnrolling
) -> TwoFactorSetup:
    """A new secret to scan (replaces a pending one). Active after /confirm."""
    from app.core import runtime_settings

    shop_name = await runtime_settings.get("shop_name", session)
    enrollment = two_factor.start_enrollment(current_user, shop_name=shop_name)
    session.add(current_user)
    await session.commit()
    return TwoFactorSetup(
        secret=enrollment.secret,
        otpauth_uri=enrollment.otpauth_uri,
        qr_svg_data_uri=enrollment.qr_svg_data_uri,
    )


@router.post("/confirm", response_model=RecoveryCodes)
async def confirm(
    request: Request,
    payload: TwoFactorCode,
    session: SessionDep,
    current_user: CurrentSuperUserEnrolling,
) -> RecoveryCodes:
    """Turn 2FA on; the recovery codes are shown this once."""
    user_id, email = current_user.id, current_user.email
    codes = two_factor.confirm(current_user, payload.code)
    session.add(current_user)
    await session.commit()
    await _journal(request, "auth.2fa.enabled", user_id, email)
    return RecoveryCodes(recovery_codes=codes)


@router.post("/recovery-codes", response_model=RecoveryCodes)
async def regenerate_recovery_codes(
    request: Request,
    payload: TwoFactorCode,
    session: SessionDep,
    current_user: CurrentSuperUserEnrolling,
) -> RecoveryCodes:
    user_id, email = current_user.id, current_user.email
    codes = two_factor.regenerate_recovery_codes(current_user, payload.code)
    session.add(current_user)
    await session.commit()
    await _journal(request, "auth.2fa.recovery_codes", user_id, email)
    return RecoveryCodes(recovery_codes=codes)


@router.post("/disable", response_model=TwoFactorStatus)
async def disable(
    request: Request,
    payload: TwoFactorDisable,
    session: SessionDep,
    current_user: CurrentSuperUserEnrolling,
) -> TwoFactorStatus:
    """Turn 2FA off: the password and a current (or recovery) code."""
    user_id, email = current_user.id, current_user.email
    if not current_user.totp_enabled:
        return _status(current_user)
    if not verify_password(payload.password, current_user.hashed_password):
        raise AppError(
            code="auth.password.invalid",
            status_code=400,
            message="Mot de passe incorrect",
            details={},
        )
    if two_factor.verify_second_factor(current_user, payload.code) is None:
        raise AppError(
            code="auth.totp.invalid",
            status_code=400,
            message="Code incorrect",
            details={},
        )
    two_factor.disable(current_user)
    session.add(current_user)
    await session.commit()
    await session.refresh(current_user)
    await _journal(request, "auth.2fa.disabled", user_id, email)
    return _status(current_user)
