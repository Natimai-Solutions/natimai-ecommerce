"""Réinitialisation de mot de passe oublié (PP-F).

Les colonnes ``password_reset_token`` et ``password_reset_token_expires``
existaient sur ``User`` sans qu'aucune route ne les utilise : un client ayant
perdu son mot de passe n'avait aucun moyen de rentrer dans son compte.

Trois précautions structurent ce flux :

* **Ne rien révéler.** La demande répond toujours la même chose, que l'adresse
  ait un compte ou non. Sans cela, l'endpoint devient un test d'existence de
  compte plus commode encore que le login — lequel a justement été durci pour
  ça (S4).
* **Stocker un condensat, pas le jeton.** Le jeton part par email ; la base n'en
  garde que le SHA-256. Une fuite de la table ne permet donc pas de prendre la
  main sur les comptes.
* **Invalider les sessions.** Un changement de mot de passe révoque les refresh
  tokens : si le mot de passe a été perdu parce qu'il était compromis, laisser
  vivre les sessions existantes viderait l'opération de son sens.
"""

from __future__ import annotations

import datetime
import logging
import secrets

from fastapi import APIRouter, Request
from pydantic import BaseModel, EmailStr, Field
from sqlmodel import col, select

from app.api.deps import SessionDep
from app.core import runtime_settings
from app.core.config import settings
from app.core.errors import AppError
from app.core.rate_limit import get_client_ip, hit_rate_limit
from app.core.security import get_password_hash, hash_reset_token
from app.features.notification.email_renderer import render_email
from app.features.notification.providers import (
    NotificationMessage,
    UnknownNotificationProviderError,
    get_notification_provider,
)
from app.features.user.crud.refresh_token import crud_user_refresh_token
from app.features.user.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["login"])

#: Durée de validité du lien. Court : c'est un jeton de reprise de compte
#: envoyé par email, un canal qu'on ne maîtrise pas.
RESET_TOKEN_TTL_MINUTES = 30


class ForgotPasswordRequest(BaseModel):
    """Demande d'envoi d'un lien de réinitialisation."""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Nouveau mot de passe, accompagné du jeton reçu par email."""

    token: str = Field(..., min_length=16, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)


class OkMessage(BaseModel):
    """Acquittement générique."""

    message: str


#: Réponse volontairement identique dans tous les cas — voir le docstring.
_NEUTRAL_RESPONSE = OkMessage(
    message=(
        "Si un compte existe pour cette adresse, un lien de réinitialisation "
        "vient d'être envoyé."
    )
)


def _utcnow() -> datetime.datetime:
    """Horodatage UTC conscient du fuseau, comme le reste du schéma (timestamptz)."""
    return datetime.datetime.now(datetime.timezone.utc)


async def _send_reset_email(email: str, token: str) -> None:
    reset_url = f"{settings.FRONTEND_HOST.rstrip('/')}/reinitialiser?token={token}"
    rendered = render_email(
        "password_reset",
        reset_url=reset_url,
        valid_minutes=RESET_TOKEN_TTL_MINUTES,
        shop_name=runtime_settings.peek("shop_name"),
    )
    try:
        provider = get_notification_provider(
            settings.PAYMENT_NOTIFICATIONS_EMAIL_PROVIDER
        )
    except UnknownNotificationProviderError:
        provider = get_notification_provider("noop")

    result = await provider.send(
        NotificationMessage(
            channel="email",
            recipient=email,
            subject=rendered.subject,
            text=rendered.text,
            html=rendered.html,
            metadata={"event_type": "password.reset_requested"},
        )
    )
    if not result.delivered:
        logger.warning(
            "password reset email not delivered to %s: %s", email, result.error
        )
    if settings.ENVIRONMENT == "local":
        # Confort de développement : sans mailer configuré, le lien n'existerait
        # nulle part. Jamais journalisé hors local.
        logger.info("[DEV] password reset link for %s = %s", email, reset_url)


@router.post("/login/forgot-password", response_model=OkMessage)
async def forgot_password(
    body: ForgotPasswordRequest,
    session: SessionDep,
    request: Request,
) -> OkMessage:
    """Envoyer un lien de réinitialisation, sans révéler si le compte existe."""
    client_ip = get_client_ip(request)
    if await hit_rate_limit(
        f"password-reset:ip:{client_ip}",
        limit=settings.PASSWORD_RESET_RATE_LIMIT_ATTEMPTS,
        window_seconds=settings.PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS,
    ):
        # Le throttle protège autant la boîte du client (harcèlement par
        # renvois) que le quota du fournisseur d'emails.
        raise AppError(
            code="password_reset.rate_limited",
            status_code=429,
            message="Trop de demandes. Réessayez dans quelques minutes.",
            details={
                "retry_after_seconds": (
                    settings.PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS
                )
            },
        )

    email = str(body.email).strip().lower()
    result = await session.exec(select(User).where(col(User.email) == email))
    user = result.first()

    # Compte inexistant ou désactivé : même réponse, aucun email.
    if user is not None and user.is_active:
        token = secrets.token_urlsafe(32)
        user.password_reset_token = hash_reset_token(token)
        user.password_reset_token_expires = _utcnow() + datetime.timedelta(
            minutes=RESET_TOKEN_TTL_MINUTES
        )
        session.add(user)
        await session.commit()
        await _send_reset_email(email, token)

    return _NEUTRAL_RESPONSE


@router.post("/login/reset-password", response_model=OkMessage)
async def reset_password(
    body: ResetPasswordRequest,
    session: SessionDep,
) -> OkMessage:
    """Poser un nouveau mot de passe à partir du jeton reçu par email."""
    token_hash = hash_reset_token(body.token)
    result = await session.exec(
        select(User).where(col(User.password_reset_token) == token_hash)
    )
    user = result.first()

    expired = (
        user is not None
        and user.password_reset_token_expires is not None
        and user.password_reset_token_expires < _utcnow()
    )
    if user is None or expired or not user.is_active:
        # Un seul code d'erreur : distinguer « inconnu » de « expiré »
        # apprendrait à un attaquant qu'un jeton deviné a existé.
        raise AppError(
            code="password_reset.token.invalid",
            status_code=400,
            message="Lien de réinitialisation invalide ou expiré.",
            details={"reason": "invalid_or_expired"},
        )

    user.hashed_password = get_password_hash(body.password)
    # Jeton à usage unique.
    user.password_reset_token = None
    user.password_reset_token_expires = None
    # Le lien n'a pu être suivi que depuis la boîte mail : l'adresse est donc
    # prouvée. C'est ce qui active un compte créé par un admin (A15), dont
    # l'invitation emprunte ce même flux ; pour un compte ordinaire non
    # vérifié, c'est une preuve de plus, pas un contournement.
    user.is_verified = True
    # Le compte a pu être verrouillé par les tentatives ratées qui ont mené
    # ici : reprendre la main doit lever le verrou.
    user.failed_login_attempts = 0
    user.locked_until = None
    session.add(user)

    # Toutes les sessions ouvertes tombent : si le mot de passe a été perdu
    # parce qu'il était compromis, en laisser vivre une viderait l'opération
    # de son sens.
    await crud_user_refresh_token.revoke_all_active_for_user(
        session=session, user_id=user.id, reason="password_reset"
    )
    await session.commit()

    return OkMessage(message="Mot de passe réinitialisé. Vous pouvez vous connecter.")
