"""Two-factor authentication of the administrators (R6).

Flow: :func:`start_enrollment` stores a fresh secret (encrypted, not yet
active) and returns what the authenticator app needs; :func:`confirm` turns it
on once the admin types a valid code, and hands out the recovery codes —
shown once, stored hashed. From then on the sign-in of that superuser needs a
code (:func:`verify_second_factor`): a current TOTP code (each time step
accepted once) or an unused recovery code (consumed).

Where the setting asks for it (``ADMIN_2FA_REQUIRED``, on by default in
production), a superuser without 2FA can sign in but only reach the
enrollment endpoints until it is set up (see ``app.api.deps``).

Nothing here commits: callers own the transaction.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone

from app.core import totp
from app.core.config import settings
from app.core.errors import AppError
from app.core.secrets_box import decrypt_json, encrypt_json
from app.features.user.models.user import User

RECOVERY_CODE_COUNT = 10


@dataclass(frozen=True, slots=True)
class Enrollment:
    secret: str
    otpauth_uri: str
    #: ``data:image/svg+xml;base64,…`` — the QR code of ``otpauth_uri``.
    qr_svg_data_uri: str


def _issuer(shop_name: str | None = None) -> str:
    return f"{shop_name or settings.SHOP_NAME} admin"


def _qr_data_uri(content: str) -> str:
    import segno

    buffer = io.BytesIO()
    segno.make(content, error="m").save(buffer, kind="svg", scale=5, border=2)
    return "data:image/svg+xml;base64," + base64.b64encode(buffer.getvalue()).decode()


def _hash_recovery(code: str) -> str:
    normalized = code.strip().replace("-", "").replace(" ", "").upper()
    return hashlib.sha256(normalized.encode()).hexdigest()


def _new_recovery_codes() -> list[str]:
    codes = []
    for _ in range(RECOVERY_CODE_COUNT):
        raw = base64.b32encode(secrets.token_bytes(5)).decode()  # 8 chars
        codes.append(f"{raw[:4]}-{raw[4:]}")
    return codes


def _secret(user: User) -> str | None:
    return decrypt_json(user.totp_secret_encrypted).get("secret")


def start_enrollment(user: User, *, shop_name: str | None = None) -> Enrollment:
    """Store a new pending secret (replacing any pending one).

    ``shop_name`` (runtime setting) names the account in the authenticator.
    """
    if user.totp_enabled:
        raise AppError(
            code="auth.totp.already_enabled",
            status_code=409,
            message="La double authentification est déjà active",
            details={},
        )
    secret = totp.generate_secret()
    user.totp_secret_encrypted = encrypt_json({"secret": secret})
    user.totp_last_step = None
    uri = totp.provisioning_uri(secret, account=user.email, issuer=_issuer(shop_name))
    return Enrollment(secret=secret, otpauth_uri=uri, qr_svg_data_uri=_qr_data_uri(uri))


def confirm(user: User, code: str) -> list[str]:
    """Activate 2FA with a first valid code; returns the recovery codes."""
    if user.totp_enabled:
        raise AppError(
            code="auth.totp.already_enabled",
            status_code=409,
            message="La double authentification est déjà active",
            details={},
        )
    secret = _secret(user)
    if not secret:
        raise AppError(
            code="auth.totp.not_started",
            status_code=400,
            message="Commencez par générer le code à scanner",
            details={},
        )
    step = totp.matching_step(secret, code)
    if step is None:
        raise AppError(
            code="auth.totp.invalid",
            status_code=400,
            message="Code incorrect : vérifiez l'heure du téléphone et réessayez",
            details={},
        )
    codes = _new_recovery_codes()
    user.totp_enabled = True
    user.totp_enabled_at = datetime.now(timezone.utc)
    user.totp_last_step = step
    user.totp_recovery_hashes = [_hash_recovery(c) for c in codes]
    return codes


def verify_second_factor(user: User, code: str | None) -> str | None:
    """Check a sign-in code: ``"totp"``, ``"recovery"`` (consumed), or None.

    A TOTP code is accepted once per time step (the step is remembered);
    a recovery code once ever.
    """
    if not code or not code.strip():
        return None
    secret = _secret(user)
    if secret:
        step = totp.matching_step(secret, code)
        if step is not None and (
            user.totp_last_step is None or step > user.totp_last_step
        ):
            user.totp_last_step = step
            return "totp"
    hashes = list(user.totp_recovery_hashes or [])
    candidate = _hash_recovery(code)
    for stored in hashes:
        if hmac.compare_digest(stored, candidate):
            hashes.remove(stored)
            user.totp_recovery_hashes = hashes
            return "recovery"
    return None


def regenerate_recovery_codes(user: User, code: str) -> list[str]:
    """New recovery codes (the old ones stop working), after a valid code."""
    if not user.totp_enabled or verify_second_factor(user, code) is None:
        raise AppError(
            code="auth.totp.invalid",
            status_code=400,
            message="Code incorrect",
            details={},
        )
    codes = _new_recovery_codes()
    user.totp_recovery_hashes = [_hash_recovery(c) for c in codes]
    return codes


def disable(user: User) -> None:
    """Turn 2FA off and forget the secret (callers check who may do it)."""
    user.totp_enabled = False
    user.totp_enabled_at = None
    user.totp_secret_encrypted = None
    user.totp_last_step = None
    user.totp_recovery_hashes = None


def remaining_recovery_codes(user: User) -> int:
    return len(user.totp_recovery_hashes or [])


__all__ = [
    "RECOVERY_CODE_COUNT",
    "Enrollment",
    "confirm",
    "disable",
    "regenerate_recovery_codes",
    "remaining_recovery_codes",
    "start_enrollment",
    "verify_second_factor",
]
