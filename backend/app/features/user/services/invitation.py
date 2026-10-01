"""Invitation d'un compte créé par un administrateur (A15).

Un compte créé depuis le back-office n'a pas de mot de passe connu de qui que
ce soit : la personne invitée en choisit un elle-même en suivant un lien reçu
par email. Ce lien réutilise le mécanisme « mot de passe oublié » — même
colonne ``password_reset_token`` (condensat SHA-256), même page vitrine, même
endpoint ``POST /login/reset-password`` — plutôt qu'un second jeu de jetons
qu'il faudrait durcir et tester à part.

Deux différences avec la réinitialisation classique :

* la durée de vie est **longue** (72 h) : l'invité n'attend pas l'email, il le
  découvre ;
* le compte est marqué **vérifié** au moment où le lien est consommé, ce que
  fait déjà ``reset_password``.
"""

from __future__ import annotations

import datetime
import logging
import secrets

from app.core import runtime_settings
from app.core.config import settings
from app.core.security import get_password_hash, hash_reset_token
from app.features.notification.email_renderer import render_email
from app.features.notification.providers import (
    NotificationMessage,
    UnknownNotificationProviderError,
    get_notification_provider,
)
from app.features.user.models.user import User

logger = logging.getLogger(__name__)

#: Validité du lien d'invitation. Bien plus long qu'une réinitialisation
#: (30 min) : l'invité ne guette pas sa boîte mail.
INVITATION_TOKEN_TTL_HOURS = 72


def _utcnow() -> datetime.datetime:
    """Horodatage UTC conscient du fuseau, comme le reste du schéma (timestamptz)."""
    return datetime.datetime.now(datetime.timezone.utc)


def unusable_password_hash() -> str:
    """Empreinte d'un mot de passe que personne ne connaît.

    ``User.hashed_password`` est non nul ; un compte invité doit pourtant
    n'être ouvrable qu'après avoir suivi le lien. Hacher 32 octets aléatoires
    jetés aussitôt donne une empreinte valide contre laquelle aucune saisie
    ne réussira — et qui ne se distingue pas d'une autre en base.
    """
    return get_password_hash(secrets.token_urlsafe(32))


def issue_invitation_token(user: User) -> str:
    """Poser un jeton d'invitation sur ``user`` et renvoyer sa valeur en clair.

    Ne commit pas : l'appelant décide de la transaction. Un jeton précédent
    (invitation renvoyée) est simplement remplacé — un seul lien valide à la
    fois.
    """
    token = secrets.token_urlsafe(32)
    user.password_reset_token = hash_reset_token(token)
    user.password_reset_token_expires = _utcnow() + datetime.timedelta(
        hours=INVITATION_TOKEN_TTL_HOURS
    )
    return token


def build_invitation_url(token: str) -> str:
    """Lien de la page vitrine de choix du mot de passe, en mode invitation."""
    return f"{settings.FRONTEND_HOST.rstrip('/')}/reinitialiser?token={token}&mode=invitation"


async def send_invitation_email(
    *, email: str, token: str, full_name: str | None
) -> bool:
    """Envoyer l'email d'invitation ; renvoie True s'il est parti.

    L'échec d'envoi n'est pas une exception : le compte existe déjà, l'admin
    voit dans la liste que l'invitation est en attente et peut la renvoyer.
    """
    invitation_url = build_invitation_url(token)
    rendered = render_email(
        "account_invitation",
        invitation_url=invitation_url,
        full_name=full_name,
        valid_hours=INVITATION_TOKEN_TTL_HOURS,
        shop_name=await runtime_settings.get("shop_name"),
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
            metadata={"event_type": "user.invited"},
        )
    )
    if not result.delivered:
        logger.warning("invitation email not delivered to %s: %s", email, result.error)
    if settings.ENVIRONMENT == "local":
        # Confort de développement : sans mailer, le lien n'existerait nulle
        # part. Jamais journalisé hors local.
        logger.info("[DEV] invitation link for %s = %s", email, invitation_url)
    return bool(result.delivered)
