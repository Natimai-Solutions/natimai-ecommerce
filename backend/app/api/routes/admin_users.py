"""Back-office des comptes utilisateurs (A15).

GET   /admin/users                          — liste (recherche, filtre groupe / actif)
POST  /admin/users                          — créer un compte + email d'invitation
PATCH /admin/users/{id}                     — nom, téléphone, groupe, activation
POST  /admin/users/{id}/resend-invitation   — renvoyer le lien tant que le compte
                                               n'a jamais été ouvert

Jusqu'ici l'admin ne voyait les clients qu'au détour d'une commande ou d'une
demande de groupe ; créer un compte pour un client pro rencontré au téléphone
exigeait de lui faire suivre le parcours d'inscription vitrine. L'affectation
directe de groupe (A9, ``POST /admin/users/{id}/assign-price-group``) existait
sans écran faute de liste pour retrouver l'utilisateur — ce module la rend
utilisable et l'englobe dans le PATCH.
"""

from __future__ import annotations

import datetime
import logging
import uuid

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func
from sqlmodel import col, or_, select

from app.api.deps import CurrentSuperUser, SessionDep
from app.core.errors import AppError
from app.features.product.models.price_group import PriceGroup
from app.features.user.crud.refresh_token import crud_user_refresh_token
from app.features.user.models.user import User
from app.features.user.services.invitation import (
    issue_invitation_token,
    send_invitation_email,
    unusable_password_hash,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/users", tags=["admin-users"])


# ---------------------------------------------------------------------------
# Schémas
# ---------------------------------------------------------------------------


class AdminUserItem(BaseModel):
    """Un compte tel que le back-office le voit.

    Rien de secret n'en sort : ni empreinte, ni jeton. ``invitation_expires_at``
    n'est renseigné que tant que le compte n'a jamais été ouvert — c'est ce
    qui distingue « invité, en attente » de « client actif ».
    """

    id: uuid.UUID
    email: str
    full_name: str | None
    phone: str | None
    is_active: bool
    is_superuser: bool
    is_verified: bool
    price_group_id: uuid.UUID | None
    price_group_code: str | None = None
    price_group_label: str | None = None
    created_at: datetime.datetime | None
    last_login: datetime.datetime | None
    locked_until: datetime.datetime | None
    #: Vrai tant que personne ne s'est jamais connecté avec ce compte.
    invitation_pending: bool
    invitation_expires_at: datetime.datetime | None


class AdminUsersPublic(BaseModel):
    """Page de résultats."""

    data: list[AdminUserItem]
    count: int


class AdminUserCreate(BaseModel):
    """Création d'un compte par un admin. Pas de mot de passe : l'invité le
    choisit lui-même via le lien reçu."""

    email: EmailStr
    full_name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=255)
    price_group_id: uuid.UUID | None = None
    is_superuser: bool = False
    #: Désactivable pour créer un compte « à blanc » (import, test) sans
    #: solliciter la personne ; l'invitation peut être envoyée plus tard.
    send_invitation: bool = True


class AdminUserUpdate(BaseModel):
    """Champs modifiables. Tous optionnels : seuls ceux fournis changent."""

    full_name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=255)
    price_group_id: uuid.UUID | None = None
    is_active: bool | None = None


class InvitationResult(BaseModel):
    """Acquittement de l'envoi d'une invitation."""

    user: AdminUserItem
    email_sent: bool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utcnow_naive() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def invitation_pending(user: User) -> bool:
    """Un compte est « en attente » tant que personne n'a ni suivi le lien
    (ce qui pose ``is_verified``) ni ouvert de session."""
    return not user.is_verified and user.last_login is None


def _to_item(user: User, group: PriceGroup | None) -> AdminUserItem:
    pending = invitation_pending(user)
    return AdminUserItem(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        phone=user.phone,
        is_active=user.is_active,
        is_superuser=user.is_superuser,
        is_verified=user.is_verified,
        price_group_id=user.price_group_id,
        price_group_code=group.code if group is not None else None,
        price_group_label=group.label if group is not None else None,
        created_at=user.created_at,
        last_login=user.last_login,
        locked_until=user.locked_until,
        invitation_pending=pending,
        invitation_expires_at=user.password_reset_token_expires if pending else None,
    )


async def _load_user(session: SessionDep, user_id: uuid.UUID) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise AppError(
            code="auth.user.not_found",
            status_code=404,
            message=f"User '{user_id}' not found",
            details={"user_id": str(user_id)},
        )
    return user


async def _load_active_price_group(
    session: SessionDep, price_group_id: uuid.UUID
) -> PriceGroup:
    group = await session.get(PriceGroup, price_group_id)
    if group is None or not group.is_active:
        raise AppError(
            code="resource.not_found",
            status_code=404,
            message=f"Price group '{price_group_id}' not found",
            details={"resource": "price_group", "id": str(price_group_id)},
        )
    return group


async def _group_of(session: SessionDep, user: User) -> PriceGroup | None:
    if user.price_group_id is None:
        return None
    return await session.get(PriceGroup, user.price_group_id)


# ---------------------------------------------------------------------------
# Liste
# ---------------------------------------------------------------------------


@router.get("", response_model=AdminUsersPublic)
async def list_users(
    session: SessionDep,
    _current_user: CurrentSuperUser,
    q: str | None = Query(
        default=None,
        max_length=255,
        description="Recherche sur l'email ou le nom (insensible à la casse)",
    ),
    price_group_id: uuid.UUID | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    pending: bool | None = Query(
        default=None,
        alias="invitation_pending",
        description="True : invitations en attente ; False : comptes ouverts",
    ),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> AdminUsersPublic:
    """Lister les comptes, les plus récents d'abord."""
    stmt = select(User)
    if q:
        needle = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(col(User.email).ilike(needle), col(User.full_name).ilike(needle))
        )
    if price_group_id is not None:
        stmt = stmt.where(User.price_group_id == price_group_id)
    if is_active is not None:
        stmt = stmt.where(col(User.is_active).is_(is_active))
    pending_clause = col(User.is_verified).is_(False) & col(User.last_login).is_(None)
    if pending is True:
        stmt = stmt.where(pending_clause)
    elif pending is False:
        stmt = stmt.where(~pending_clause)

    total = (
        await session.exec(select(func.count()).select_from(stmt.subquery()))
    ).one()

    page_stmt = (
        stmt.order_by(col(User.created_at).desc().nulls_last(), col(User.email))
        .offset(skip)
        .limit(limit)
    )
    users = list((await session.exec(page_stmt)).all())

    groups: dict[uuid.UUID, PriceGroup] = {}
    group_ids = {u.price_group_id for u in users if u.price_group_id is not None}
    if group_ids:
        rows = await session.exec(
            select(PriceGroup).where(col(PriceGroup.id).in_(group_ids))
        )
        groups = {g.id: g for g in rows}

    return AdminUsersPublic(
        data=[
            _to_item(u, groups.get(u.price_group_id) if u.price_group_id else None)
            for u in users
        ],
        count=int(total),
    )


# ---------------------------------------------------------------------------
# Création + invitation
# ---------------------------------------------------------------------------


@router.post("", response_model=InvitationResult, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: AdminUserCreate,
    session: SessionDep,
    current_user: CurrentSuperUser,
) -> InvitationResult:
    """Créer un compte et, sauf demande contraire, envoyer l'invitation.

    Le compte est créé **avant** l'envoi : un email qui ne part pas n'annule
    pas la création, l'admin le voit (``email_sent``) et peut renvoyer.
    """
    email = str(payload.email).strip().lower()
    existing = (
        await session.exec(select(User).where(col(User.email) == email))
    ).first()
    if existing is not None:
        raise AppError(
            code="admin.user.email_taken",
            status_code=409,
            message="Un compte existe déjà pour cette adresse",
            details={"email": email, "user_id": str(existing.id)},
        )

    if payload.price_group_id is not None:
        await _load_active_price_group(session, payload.price_group_id)

    admin_id = current_user.id  # capturé avant commit (MissingGreenlet)
    user = User(
        email=email,
        full_name=payload.full_name,
        phone=payload.phone,
        price_group_id=payload.price_group_id,
        is_superuser=payload.is_superuser,
        is_active=True,
        # Prouvée seulement quand le lien est suivi (reset_password le pose).
        is_verified=False,
        hashed_password=unusable_password_hash(),
        created_at=_utcnow_naive(),
        created_by_id=admin_id,
    )
    token = issue_invitation_token(user) if payload.send_invitation else None
    session.add(user)
    await session.commit()
    await session.refresh(user)

    email_sent = False
    if token is not None:
        email_sent = await send_invitation_email(
            email=email, token=token, full_name=user.full_name
        )

    logger.info(
        "Admin created user: user_id=%s email=%s superuser=%s invited=%s admin=%s",
        user.id,
        email,
        payload.is_superuser,
        token is not None,
        admin_id,
    )
    # Rechargé après le commit : l'instance validée plus haut est expirée.
    group = await _group_of(session, user)
    return InvitationResult(user=_to_item(user, group), email_sent=email_sent)


@router.post("/{user_id}/resend-invitation", response_model=InvitationResult)
async def resend_invitation(
    user_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentSuperUser,
) -> InvitationResult:
    """Renvoyer un lien d'invitation (le précédent cesse de fonctionner).

    Refusé dès que le compte a été ouvert une fois : à partir de là, c'est
    « mot de passe oublié » qui s'applique, à l'initiative de la personne —
    un admin ne doit pas pouvoir reprendre la main sur un compte actif.
    """
    user = await _load_user(session, user_id)
    if not invitation_pending(user):
        raise AppError(
            code="admin.user.already_activated",
            status_code=409,
            message="Ce compte a déjà été activé : l'invitation n'a plus d'objet",
            details={"user_id": str(user_id)},
        )
    if not user.is_active:
        raise AppError(
            code="admin.user.inactive",
            status_code=409,
            message="Compte désactivé : réactivez-le avant de renvoyer l'invitation",
            details={"user_id": str(user_id)},
        )

    admin_id = current_user.id
    email = user.email
    full_name = user.full_name
    token = issue_invitation_token(user)
    session.add(user)
    await session.commit()
    await session.refresh(user)

    email_sent = await send_invitation_email(
        email=email, token=token, full_name=full_name
    )
    logger.info(
        "Invitation resent: user_id=%s sent=%s admin=%s", user_id, email_sent, admin_id
    )
    group = await _group_of(session, user)
    return InvitationResult(user=_to_item(user, group), email_sent=email_sent)


# ---------------------------------------------------------------------------
# Modification
# ---------------------------------------------------------------------------


@router.patch("/{user_id}", response_model=AdminUserItem)
async def update_user(
    user_id: uuid.UUID,
    payload: AdminUserUpdate,
    session: SessionDep,
    current_user: CurrentSuperUser,
) -> AdminUserItem:
    """Modifier nom, téléphone, groupe de prix ou activation.

    Désactiver un compte coupe aussi ses sessions ouvertes : sans cela la
    personne resterait connectée jusqu'à expiration de son refresh token.
    """
    user = await _load_user(session, user_id)
    fields = payload.model_dump(exclude_unset=True)

    if fields.get("is_active") is False and user.id == current_user.id:
        raise AppError(
            code="admin.user.self_deactivation",
            status_code=400,
            message="Vous ne pouvez pas désactiver votre propre compte",
            details={"user_id": str(user_id)},
        )

    if "price_group_id" in fields and fields["price_group_id"] is not None:
        await _load_active_price_group(session, fields["price_group_id"])

    for name, value in fields.items():
        setattr(user, name, value)
    user.modify_at = _utcnow_naive()
    user.modify_by_id = current_user.id
    session.add(user)

    if fields.get("is_active") is False:
        await crud_user_refresh_token.revoke_all_active_for_user(
            session=session, user_id=user_id, reason="admin_deactivated"
        )

    await session.commit()
    await session.refresh(user)
    logger.info(
        "Admin updated user: user_id=%s fields=%s admin=%s",
        user_id,
        sorted(fields),
        user.modify_by_id,
    )
    group = await _group_of(session, user)
    return _to_item(user, group)
