"""Commande sans compte : le compte « invité » ouvert au paiement.

Le tunnel de commande (adresses, devis, livraison, paiement, suivi) repose sur
un compte. Plutôt que d'en écrire un second pour les visiteurs, le paiement
ouvre un compte **sans mot de passe**, marqué ``is_guest``, et la session du
navigateur qui l'a créé : la suite est le tunnel de tout le monde.

Trois règles en découlent :

* **Jamais de session sur un compte existant.** Une adresse e-mail déjà
  connue n'ouvre rien : sans quoi taper l'e-mail d'un autre suffirait à lire
  ses commandes et ses adresses. Un ancien invité reçoit un lien pour
  reprendre son compte ; un client se connecte.
* **Le compte devient un compte client par la preuve de l'adresse** : le lien
  reçu par e-mail (même jeton que l'invitation admin, A15), l'inscription par
  code e-mail ou une connexion OAuth vérifiée. Les sessions ouvertes jusque-là
  tombent : rien ne prouvait que le navigateur de départ était le sien.
* **Le compte est proposé, pas imposé** : après la commande, la vitrine offre
  d'envoyer ce lien ; le suivi passe sinon par le lien signé des e-mails.
"""

from __future__ import annotations

import logging

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core import runtime_settings
from app.core.config import settings
from app.core.security import new_security_stamp
from app.features.notification.email_renderer import render_email
from app.features.notification.mailer import queue_email
from app.features.user.crud.refresh_token import crud_user_refresh_token
from app.features.user.models.user import User
from app.features.user.services.invitation import (
    INVITATION_TOKEN_TTL_HOURS,
    build_invitation_url,
    issue_invitation_token,
    unusable_password_hash,
)

logger = logging.getLogger(__name__)


def new_guest_user(*, email: str, full_name: str, phone: str | None) -> User:
    """A passwordless, unverified customer account (not added to the session)."""
    return User(
        email=email,
        full_name=full_name,
        phone=phone,
        is_active=True,
        is_verified=False,
        is_guest=True,
        hashed_password=unusable_password_hash(),
    )


async def claim_guest_account(session: AsyncSession, user: User) -> None:
    """The owner of the address takes the account over (no commit).

    Every session opened so far is closed: it was opened by whoever typed the
    address at checkout, which proves nothing.
    """
    if not user.is_guest:
        return
    user.is_guest = False
    user.is_verified = True
    user.security_stamp = new_security_stamp()
    session.add(user)
    await crud_user_refresh_token.revoke_all_active_for_user(
        session=session, user_id=user.id, reason="guest_claimed"
    )


async def send_guest_activation_link(session: AsyncSession, user: User) -> None:
    """E-mail the link that turns the guest account into a customer account.

    Same token as an admin invitation: the link opens the « choisir un mot de
    passe » page, and following it proves the address. Commits the token.
    """
    email = user.email
    full_name = user.full_name
    token = issue_invitation_token(user)
    session.add(user)
    await session.commit()
    url = build_invitation_url(token)
    rendered = render_email(
        "guest_account",
        activation_url=url,
        full_name=full_name,
        valid_hours=INVITATION_TOKEN_TTL_HOURS,
        shop_name=await runtime_settings.get("shop_name"),
    )
    await queue_email(
        session,
        recipient=email,
        subject=rendered.subject,
        text=rendered.text,
        html=rendered.html,
        event_type="user.guest_activation",
        resendable=False,  # carries a valid link
    )
    if settings.ENVIRONMENT == "local":
        # Sans mailer en local, le lien n'existerait nulle part. Jamais
        # journalisé hors local.
        logger.info("[DEV] guest activation link for %s = %s", email, url)


__all__ = [
    "claim_guest_account",
    "new_guest_user",
    "send_guest_activation_link",
]
