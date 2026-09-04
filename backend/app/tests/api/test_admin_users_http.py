"""Contrat HTTP du back-office des comptes (A15), via l'application complète.

Vérifie ce que les tests unitaires ne voient pas : la garde superuser sur les
routes, et le fait qu'une connexion réelle horodate ``last_login`` — c'est ce
qui fait qu'un admin qui vient de se connecter n'apparaît pas « en attente ».
"""

from fastapi.testclient import TestClient

from app.core.config import settings


def test_the_listing_is_superuser_only(
    client: TestClient, normal_user_token_headers: dict[str, str]
) -> None:
    anonymous = client.get(f"{settings.API_V1_STR}/admin/users")
    assert anonymous.status_code == 401

    customer = client.get(
        f"{settings.API_V1_STR}/admin/users", headers=normal_user_token_headers
    )
    assert customer.status_code == 403


def test_a_logged_in_admin_is_listed_as_opened(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """La fixture vient de se connecter par mot de passe : la trace doit être là."""
    response = client.get(
        f"{settings.API_V1_STR}/admin/users",
        headers=superuser_token_headers,
        params={"q": settings.FIRST_SUPERUSER},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["count"] >= 1
    me = next(u for u in body["data"] if u["email"] == settings.FIRST_SUPERUSER)
    assert me["last_login"] is not None
    assert me["invitation_pending"] is False
    assert me["is_superuser"] is True
    # Rien de secret ne sort.
    assert "hashed_password" not in me
    assert "password_reset_token" not in me


def test_creation_rejects_a_malformed_email(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    response = client.post(
        f"{settings.API_V1_STR}/admin/users",
        headers=superuser_token_headers,
        json={"email": "pas-une-adresse"},
    )
    assert response.status_code == 422
