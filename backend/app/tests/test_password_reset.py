"""Réinitialisation de mot de passe oublié (PP-F).

Les colonnes existaient sans route : un client ayant perdu son mot de passe
n'avait aucun moyen de rentrer. Ce qui doit être verrouillé ici tient en trois
propriétés — ne rien révéler, ne pas stocker le jeton en clair, et couper les
sessions ouvertes.
"""

from __future__ import annotations

import datetime
import uuid
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Request

from app.api.routes import password_reset as module
from app.api.routes.password_reset import (
    ForgotPasswordRequest,
    ResetPasswordRequest,
    forgot_password,
    reset_password,
)
from app.core.errors import AppError
from app.core.security import hash_reset_token

#: Le schéma impose 16 caractères minimum — un jeton court trahirait une
#: génération affaiblie, donc les tests utilisent une valeur réaliste.
_VALID_TOKEN = "jeton-de-test-suffisamment-long"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _no_throttle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "hit_rate_limit", AsyncMock(return_value=False))
    monkeypatch.setattr(module, "get_client_ip", lambda _request: "10.0.0.1")


def _request() -> Request:
    """Stub minimal : seule get_client_ip touche la requête, et il est mocké."""
    return cast(
        Request, SimpleNamespace(headers={}, client=SimpleNamespace(host="10.0.0.1"))
    )


def _session(user: object | None) -> MagicMock:
    result = MagicMock()
    result.first = MagicMock(return_value=user)
    session = MagicMock()
    session.exec = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


def _user(**overrides: object) -> SimpleNamespace:
    user = SimpleNamespace(
        id=uuid.uuid4(),
        email="client@example.pf",
        is_active=True,
        hashed_password="ancien",
        password_reset_token=None,
        password_reset_token_expires=None,
        failed_login_attempts=3,
        locked_until=datetime.datetime(2026, 1, 1),
    )
    for key, value in overrides.items():
        setattr(user, key, value)
    return user


def test_the_token_is_never_stored_in_clear() -> None:
    """Une fuite de la table ne doit pas permettre de prendre les comptes."""
    token = "un-jeton-tres-aleatoire-de-32-octets"
    digest = hash_reset_token(token)

    assert digest != token
    assert token not in digest
    assert len(digest) == 64  # SHA-256 hexadécimal
    assert hash_reset_token(token) == digest  # déterministe, donc recherchable


@pytest.mark.anyio
async def test_an_unknown_address_gets_the_same_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sinon l'endpoint devient un test d'existence de compte plus commode
    encore que le login, que S4 a justement durci pour ça."""
    sent = AsyncMock()
    monkeypatch.setattr(module, "_send_reset_email", sent)

    known = await forgot_password(
        ForgotPasswordRequest(email="client@example.pf"),
        _session(_user()),
        _request(),
    )
    unknown = await forgot_password(
        ForgotPasswordRequest(email="personne@example.pf"),
        _session(None),
        _request(),
    )

    assert known.message == unknown.message
    # Et aucun email n'est parti pour l'adresse inconnue.
    assert sent.await_count == 1


@pytest.mark.anyio
async def test_a_deactivated_account_receives_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = AsyncMock()
    monkeypatch.setattr(module, "_send_reset_email", sent)

    response = await forgot_password(
        ForgotPasswordRequest(email="client@example.pf"),
        _session(_user(is_active=False)),
        _request(),
    )

    assert response.message
    sent.assert_not_awaited()


@pytest.mark.anyio
async def test_the_stored_token_is_the_digest_of_the_emailed_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    async def _capture(email: str, token: str) -> None:
        captured["email"] = email
        captured["token"] = token

    monkeypatch.setattr(module, "_send_reset_email", _capture)
    user = _user()

    await forgot_password(
        ForgotPasswordRequest(email="client@example.pf"), _session(user), _request()
    )

    assert user.password_reset_token == hash_reset_token(captured["token"])
    assert user.password_reset_token_expires is not None


@pytest.mark.anyio
async def test_the_request_is_throttled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Protège la boîte du client autant que le quota du mailer."""
    monkeypatch.setattr(module, "hit_rate_limit", AsyncMock(return_value=True))

    with pytest.raises(AppError) as exc:
        await forgot_password(
            ForgotPasswordRequest(email="client@example.pf"),
            _session(_user()),
            _request(),
        )

    assert exc.value.status_code == 429
    assert exc.value.code == "password_reset.rate_limited"


@pytest.mark.anyio
async def test_resetting_replaces_the_password_and_clears_the_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revoke = AsyncMock(return_value=2)
    monkeypatch.setattr(
        "app.api.routes.password_reset.crud_user_refresh_token."
        "revoke_all_active_for_user",
        revoke,
    )
    user = _user(
        password_reset_token=hash_reset_token(_VALID_TOKEN),
        password_reset_token_expires=datetime.datetime(2099, 1, 1),
    )

    await reset_password(
        ResetPasswordRequest(token=_VALID_TOKEN, password="nouveau-mot-de-passe"),
        _session(user),
    )

    assert user.hashed_password != "ancien"
    # Jeton à usage unique.
    assert user.password_reset_token is None
    assert user.password_reset_token_expires is None
    # Le compte a pu être verrouillé par les tentatives qui ont mené ici.
    assert user.failed_login_attempts == 0
    assert user.locked_until is None
    # Un mot de passe perdu peut l'avoir été parce qu'il était compromis :
    # laisser vivre une session ouverte viderait l'opération de son sens.
    revoke.assert_awaited_once()


@pytest.mark.anyio
async def test_an_unusable_token_is_rejected_indistinctly() -> None:
    """Distinguer « inconnu » d'« expiré » apprendrait à un attaquant qu'un
    jeton deviné a existé."""
    cases = [
        _session(None),  # jeton inconnu
        _session(
            _user(
                password_reset_token=hash_reset_token(_VALID_TOKEN),
                password_reset_token_expires=datetime.datetime(2000, 1, 1),
            )
        ),  # expiré
        _session(
            _user(
                is_active=False,
                password_reset_token=hash_reset_token(_VALID_TOKEN),
                password_reset_token_expires=datetime.datetime(2099, 1, 1),
            )
        ),  # compte désactivé
    ]
    codes = set()
    for session in cases:
        with pytest.raises(AppError) as exc:
            await reset_password(
                ResetPasswordRequest(
                    token=_VALID_TOKEN, password="nouveau-mot-de-passe"
                ),
                session,
            )
        codes.add((exc.value.status_code, exc.value.code))

    assert codes == {(400, "password_reset.token.invalid")}
