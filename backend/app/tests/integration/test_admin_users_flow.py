"""Parcours complet d'un compte créé par un admin (A15), contre une vraie base.

Création → apparition dans la liste, en attente → la personne suit le lien et
choisit un mot de passe (flux « mot de passe oublié » réutilisé) → le compte
est vérifié, ouvrable avec ce mot de passe, et n'est plus « en attente ».
"""

from __future__ import annotations

import uuid
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes import admin_users as module
from app.api.routes.admin_users import (
    AdminUserCreate,
    AdminUserUpdate,
    create_user,
    list_users,
    resend_invitation,
    update_user,
)
from app.api.routes.password_reset import ResetPasswordRequest, reset_password
from app.core.errors import AppError
from app.features.product.models.price_group import PriceGroup
from app.features.user.crud.user import crud_user
from app.features.user.models.user import User


async def _seed_admin(session: AsyncSession) -> User:
    admin = User(
        email=f"admin+{uuid.uuid4().hex[:8]}@test.local",
        is_superuser=True,
        is_active=True,
        is_verified=True,
        hashed_password="x",
    )
    session.add(admin)
    await session.flush()
    return admin


async def _seed_group(session: AsyncSession) -> PriceGroup:
    group = PriceGroup(code="PRO", label="Professionnel", is_active=True)
    session.add(group)
    await session.flush()
    return group


def _last_token(sent: AsyncMock) -> str:
    """Jeton en clair passé au dernier envoi d'email (mocké)."""
    assert sent.await_args is not None
    return str(sent.await_args.kwargs["token"])


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock(return_value=True)
    monkeypatch.setattr(module, "send_invitation_email", mock)
    return mock


async def _listed(session: AsyncSession, admin: Any, **params: Any) -> list[Any]:
    page = await list_users(
        session=session,
        _current_user=admin,
        q=params.get("q"),
        price_group_id=params.get("price_group_id"),
        is_active=params.get("is_active"),
        pending=params.get("pending"),
        skip=0,
        limit=50,
    )
    return page.data


@pytest.mark.asyncio
async def test_invited_account_activates_through_the_reset_link(
    db_session: AsyncSession, sent: AsyncMock
) -> None:
    admin = await _seed_admin(db_session)
    group = await _seed_group(db_session)
    admin_id, group_id = admin.id, group.id
    email = f"invite+{uuid.uuid4().hex[:8]}@example.pf"

    created = await create_user(
        AdminUserCreate(email=email, full_name="Client Pro", price_group_id=group_id),
        db_session,
        cast(Any, admin),
    )
    assert created.email_sent is True
    assert created.user.price_group_label == "Professionnel"
    assert created.user.invitation_pending is True
    assert created.user.invitation_expires_at is not None
    token = _last_token(sent)

    # Le jeton n'apparaît pas en clair en base, et aucun mot de passe ne marche.
    row = await crud_user.get_by_email(db_session, email=email)
    assert row is not None
    assert row.password_reset_token != token
    assert (
        await crud_user.authenticate(db_session, email=email, password="password")
        is None
    )

    # Dans la liste, filtre « en attente » et recherche par nom.
    admin_row = await db_session.get(User, admin_id)
    pending = await _listed(db_session, admin_row, pending=True)
    assert [u.email for u in pending] == [email]
    by_name = await _listed(db_session, admin_row, q="client pro")
    assert [u.email for u in by_name] == [email]

    # La personne suit le lien et choisit son mot de passe.
    await reset_password(
        ResetPasswordRequest(token=token, password="mon-nouveau-secret"), db_session
    )

    activated = await crud_user.authenticate(
        db_session, email=email, password="mon-nouveau-secret"
    )
    assert activated is not None
    assert activated.is_verified is True  # le lien prouve l'adresse
    assert activated.password_reset_token is None  # usage unique

    admin_row = await db_session.get(User, admin_id)
    still_pending = await _listed(db_session, admin_row, pending=True)
    assert still_pending == []
    opened = await _listed(db_session, admin_row, pending=False, q=email)
    assert [u.email for u in opened] == [email]

    # Et l'invitation ne peut plus être renvoyée : c'est un compte actif.
    with pytest.raises(AppError) as exc:
        await resend_invitation(activated.id, db_session, cast(Any, admin_row))
    assert exc.value.code == "admin.user.already_activated"


@pytest.mark.asyncio
async def test_resent_invitation_invalidates_the_first_link(
    db_session: AsyncSession, sent: AsyncMock
) -> None:
    admin = await _seed_admin(db_session)
    admin_id = admin.id
    email = f"invite+{uuid.uuid4().hex[:8]}@example.pf"

    created = await create_user(
        AdminUserCreate(email=email), db_session, cast(Any, admin)
    )
    first_token = _last_token(sent)

    admin_row = await db_session.get(User, admin_id)
    await resend_invitation(created.user.id, db_session, cast(Any, admin_row))
    second_token = _last_token(sent)
    assert second_token != first_token

    with pytest.raises(AppError) as exc:
        await reset_password(
            ResetPasswordRequest(token=first_token, password="tentative-1234"),
            db_session,
        )
    assert exc.value.code == "password_reset.token.invalid"

    await reset_password(
        ResetPasswordRequest(token=second_token, password="valide-12345"), db_session
    )
    assert (
        await crud_user.authenticate(db_session, email=email, password="valide-12345")
        is not None
    )


@pytest.mark.asyncio
@pytest.mark.usefixtures("sent")
async def test_list_filters_by_group_and_activity(db_session: AsyncSession) -> None:
    admin = await _seed_admin(db_session)
    group = await _seed_group(db_session)
    admin_id, group_id = admin.id, group.id
    tag = uuid.uuid4().hex[:6]

    pro = await create_user(
        AdminUserCreate(email=f"pro-{tag}@example.pf", price_group_id=group_id),
        db_session,
        cast(Any, admin),
    )
    admin_row = await db_session.get(User, admin_id)
    other = await create_user(
        AdminUserCreate(email=f"autre-{tag}@example.pf"),
        db_session,
        cast(Any, admin_row),
    )

    admin_row = await db_session.get(User, admin_id)
    await update_user(
        other.user.id,
        AdminUserUpdate(is_active=False),
        db_session,
        cast(Any, admin_row),
    )

    admin_row = await db_session.get(User, admin_id)
    in_group = await _listed(db_session, admin_row, price_group_id=group_id)
    assert [u.id for u in in_group] == [pro.user.id]

    admin_row = await db_session.get(User, admin_id)
    inactive = await _listed(db_session, admin_row, is_active=False)
    assert [u.id for u in inactive] == [other.user.id]

    # Le total compte au-delà de la page, la page respecte skip/limit.
    admin_row = await db_session.get(User, admin_id)
    page = await list_users(
        session=db_session,
        _current_user=cast(Any, admin_row),
        q=tag,
        price_group_id=None,
        is_active=None,
        pending=None,
        skip=1,
        limit=1,
    )
    assert page.count == 2
    assert len(page.data) == 1
