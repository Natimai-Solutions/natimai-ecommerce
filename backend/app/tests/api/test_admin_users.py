"""Back-office des comptes (A15) — règles unitaires, session mockée.

Ce qui doit tenir ici : un compte créé par un admin n'est ouvrable que via le
lien d'invitation (jamais de mot de passe connu, jeton jamais stocké en clair),
l'invitation ne peut pas servir à reprendre un compte déjà activé, et un admin
ne peut pas se désactiver lui-même. Le flux complet contre une vraie base est
dans ``tests/integration/test_admin_users_flow.py``.
"""

from __future__ import annotations

import datetime
import uuid
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.routes import admin_users as module
from app.api.routes.admin_users import (
    AdminUserCreate,
    AdminUserUpdate,
    create_user,
    invitation_pending,
    resend_invitation,
    update_user,
)
from app.core.errors import AppError
from app.core.security import hash_reset_token, verify_password
from app.features.user.crud.refresh_token import crud_user_refresh_token
from app.features.user.services.invitation import (
    INVITATION_TOKEN_TTL_HOURS,
    build_invitation_url,
    issue_invitation_token,
    unusable_password_hash,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _admin() -> Any:
    return SimpleNamespace(id=uuid.uuid4(), is_superuser=True)


def _user(**overrides: Any) -> Any:
    user = SimpleNamespace(
        id=uuid.uuid4(),
        email="invite@example.pf",
        full_name="Invité Test",
        phone=None,
        is_active=True,
        is_superuser=False,
        is_verified=False,
        price_group_id=None,
        created_at=datetime.datetime(2026, 9, 1, 8, 0, tzinfo=datetime.UTC),
        last_login=None,
        locked_until=None,
        password_reset_token=None,
        password_reset_token_expires=None,
        modify_at=None,
        modify_by_id=None,
    )
    for key, value in overrides.items():
        setattr(user, key, value)
    return user


def _session(*, first: Any = None, get: Any = None) -> MagicMock:
    """Session dont ``exec().first()`` renvoie ``first`` et ``get()`` ``get``
    (une valeur, ou une fonction (model, id) → valeur)."""
    result = MagicMock()
    result.first = MagicMock(return_value=first)
    session = MagicMock()
    session.exec = AsyncMock(return_value=result)
    session.get = AsyncMock(side_effect=get if callable(get) else lambda *_: get)
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


def _last_token(sent: AsyncMock) -> str:
    """Jeton en clair passé au dernier envoi d'email (mocké)."""
    assert sent.await_args is not None
    return str(sent.await_args.kwargs["token"])


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock(return_value=True)
    monkeypatch.setattr(module, "send_invitation_email", mock)
    return mock


# ---------------------------------------------------------------------------
# Service d'invitation
# ---------------------------------------------------------------------------


def test_the_placeholder_password_matches_nothing_and_never_repeats() -> None:
    """Le compte doit être inouvrable avant le lien, et deux comptes invités
    ne doivent pas partager la même empreinte (sinon l'une trahit l'autre)."""
    first, second = unusable_password_hash(), unusable_password_hash()

    assert first != second
    assert not verify_password("", first)
    assert not verify_password("password", first)


def test_the_invitation_token_is_stored_hashed_with_a_long_ttl() -> None:
    user = _user()

    token = issue_invitation_token(user)

    assert len(token) >= 32
    assert user.password_reset_token == hash_reset_token(token)
    assert token not in user.password_reset_token
    remaining = user.password_reset_token_expires - datetime.datetime.now(datetime.UTC)
    # Bien plus qu'une réinitialisation (30 min) : l'invité ne guette pas sa boîte.
    assert datetime.timedelta(hours=INVITATION_TOKEN_TTL_HOURS - 1) < remaining
    assert remaining <= datetime.timedelta(hours=INVITATION_TOKEN_TTL_HOURS)


def test_the_invitation_link_lands_on_the_reset_page_in_invitation_mode() -> None:
    url = build_invitation_url("abc")

    assert url.endswith("/reinitialiser?token=abc&mode=invitation")


def test_pending_means_neither_verified_nor_ever_logged_in() -> None:
    assert invitation_pending(_user()) is True
    # Le lien a été suivi (reset_password pose is_verified) : plus en attente.
    assert invitation_pending(_user(is_verified=True)) is False
    # Un compte historique jamais vérifié mais déjà ouvert n'est pas un invité.
    assert (
        invitation_pending(
            _user(last_login=datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC))
        )
        is False
    )


# ---------------------------------------------------------------------------
# Création
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_creating_a_user_sends_one_invitation_and_stores_only_the_digest(
    sent: AsyncMock,
) -> None:
    session = _session(first=None)
    admin = _admin()

    result = await create_user(
        AdminUserCreate(email="Nouveau@Example.PF", full_name="Nouveau Client"),
        session,
        cast(Any, admin),
    )

    created = session.add.call_args.args[0]
    assert created.email == "nouveau@example.pf"  # normalisé
    assert created.is_verified is False  # prouvé seulement en suivant le lien
    assert created.created_by_id == admin.id
    sent.assert_awaited_once()
    token = _last_token(sent)
    assert created.password_reset_token == hash_reset_token(token)
    assert result.email_sent is True
    assert result.user.invitation_pending is True


@pytest.mark.anyio
async def test_creating_without_invitation_leaves_no_token(sent: AsyncMock) -> None:
    session = _session(first=None)

    result = await create_user(
        AdminUserCreate(email="blanc@example.pf", send_invitation=False),
        session,
        cast(Any, _admin()),
    )

    created = session.add.call_args.args[0]
    assert created.password_reset_token is None
    sent.assert_not_awaited()
    assert result.email_sent is False


@pytest.mark.anyio
async def test_a_failed_email_does_not_cancel_the_account(
    sent: AsyncMock,
) -> None:
    """Le compte existe, l'admin voit que l'email n'est pas parti et renvoie —
    plutôt qu'une 500 qui laisserait douter de l'état de la base."""
    sent.return_value = False
    session = _session(first=None)

    result = await create_user(
        AdminUserCreate(email="perdu@example.pf"), session, cast(Any, _admin())
    )

    session.commit.assert_awaited_once()
    assert result.email_sent is False


@pytest.mark.anyio
async def test_an_existing_email_is_a_409(sent: AsyncMock) -> None:
    session = _session(first=_user())

    with pytest.raises(AppError) as exc:
        await create_user(
            AdminUserCreate(email="invite@example.pf"), session, cast(Any, _admin())
        )

    assert exc.value.status_code == 409
    assert exc.value.code == "admin.user.email_taken"
    sent.assert_not_awaited()


@pytest.mark.anyio
async def test_an_inactive_price_group_is_refused() -> None:
    session = _session(first=None, get=SimpleNamespace(is_active=False))

    with pytest.raises(AppError) as exc:
        await create_user(
            AdminUserCreate(email="pro@example.pf", price_group_id=uuid.uuid4()),
            session,
            cast(Any, _admin()),
        )

    assert exc.value.status_code == 404
    session.commit.assert_not_awaited()


# ---------------------------------------------------------------------------
# Renvoi d'invitation
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_resending_replaces_the_previous_token(sent: AsyncMock) -> None:
    user = _user()
    first_token = issue_invitation_token(user)
    first_digest = user.password_reset_token

    await resend_invitation(user.id, _session(get=user), cast(Any, _admin()))

    new_token = _last_token(sent)
    assert new_token != first_token
    assert user.password_reset_token == hash_reset_token(new_token)
    assert user.password_reset_token != first_digest  # l'ancien lien est mort


@pytest.mark.anyio
async def test_an_activated_account_cannot_be_re_invited(sent: AsyncMock) -> None:
    """Sinon un admin reprendrait la main sur n'importe quel compte client en
    se faisant envoyer un lien — c'est « mot de passe oublié », à l'initiative
    de la personne, qui s'applique une fois le compte ouvert."""
    user = _user(
        is_verified=True,
        last_login=datetime.datetime(2026, 9, 2, tzinfo=datetime.UTC),
    )

    with pytest.raises(AppError) as exc:
        await resend_invitation(user.id, _session(get=user), cast(Any, _admin()))

    assert exc.value.status_code == 409
    assert exc.value.code == "admin.user.already_activated"
    sent.assert_not_awaited()


@pytest.mark.anyio
async def test_a_deactivated_account_is_not_re_invited(sent: AsyncMock) -> None:
    user = _user(is_active=False)

    with pytest.raises(AppError) as exc:
        await resend_invitation(user.id, _session(get=user), cast(Any, _admin()))

    assert exc.value.code == "admin.user.inactive"
    sent.assert_not_awaited()


@pytest.mark.anyio
async def test_resending_to_an_unknown_user_is_a_404() -> None:
    with pytest.raises(AppError) as exc:
        await resend_invitation(uuid.uuid4(), _session(get=None), cast(Any, _admin()))

    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# Modification
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_an_admin_cannot_deactivate_their_own_account() -> None:
    admin = _admin()
    me = _user(id=admin.id, is_superuser=True)

    with pytest.raises(AppError) as exc:
        await update_user(
            me.id, AdminUserUpdate(is_active=False), _session(get=me), cast(Any, admin)
        )

    assert exc.value.status_code == 400
    assert exc.value.code == "admin.user.self_deactivation"
    assert me.is_active is True


@pytest.mark.anyio
async def test_deactivating_cuts_open_sessions(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sans révocation, la personne resterait connectée jusqu'à expiration de
    son refresh token — la désactivation ne serait qu'un affichage."""
    revoke = AsyncMock(return_value=1)
    monkeypatch.setattr(crud_user_refresh_token, "revoke_all_active_for_user", revoke)
    user = _user(
        is_verified=True,
        last_login=datetime.datetime(2026, 9, 2, tzinfo=datetime.UTC),
    )
    admin = _admin()

    item = await update_user(
        user.id, AdminUserUpdate(is_active=False), _session(get=user), cast(Any, admin)
    )

    assert item.is_active is False
    revoke.assert_awaited_once()
    assert revoke.await_args is not None
    assert revoke.await_args.kwargs["user_id"] == user.id
    assert user.modify_by_id == admin.id


@pytest.mark.anyio
async def test_only_the_provided_fields_change(monkeypatch: pytest.MonkeyPatch) -> None:
    revoke = AsyncMock(return_value=0)
    monkeypatch.setattr(crud_user_refresh_token, "revoke_all_active_for_user", revoke)
    group_id = uuid.uuid4()
    user = _user(phone="+689 40 00 00 00")
    group = SimpleNamespace(id=group_id, is_active=True, code="PRO", label="Pro")

    def get(model: Any, _id: Any) -> Any:
        return group if model.__name__ == "PriceGroup" else user

    item = await update_user(
        user.id,
        AdminUserUpdate(price_group_id=group_id),
        _session(get=get),
        cast(Any, _admin()),
    )

    assert user.price_group_id == group_id
    assert user.phone == "+689 40 00 00 00"  # non fourni → intact
    assert user.is_active is True
    assert item.price_group_label == "Pro"
    revoke.assert_not_awaited()  # rien à couper : le compte reste actif
