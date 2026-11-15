"""ADMIN_ALLOWED_IPS applies to every superuser request, not only the
/api/v1/admin/* paths Caddy filters (audit 2026-11)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings


def test_a_superuser_acts_from_the_allowed_networks_only(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "CLIENT_IP_HEADER", "X-Forwarded-For")
    monkeypatch.setattr(settings, "ADMIN_ALLOWED_IPS", "203.0.113.0/24 2001:db8::/32")

    # A superuser route outside /api/v1/admin (Caddy does not filter it).
    outside = {**superuser_token_headers, "X-Forwarded-For": "198.51.100.7"}
    refused = client.get("/api/v1/suppliers/", headers=outside)
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "auth.admin.network_denied"

    inside = {**superuser_token_headers, "X-Forwarded-For": "203.0.113.20"}
    assert client.get("/api/v1/suppliers/", headers=inside).status_code != 403


def test_no_list_means_no_restriction(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    assert settings.ADMIN_ALLOWED_IPS in (None, "")
    response = client.get("/api/v1/users/me", headers=superuser_token_headers)
    assert response.status_code == 200


def test_optional_auth_routes_apply_the_list_too(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The generic CRUD takes an optional user: it skipped the network check,
    so a stolen admin token still wrote from anywhere."""
    monkeypatch.setattr(settings, "CLIENT_IP_HEADER", "X-Forwarded-For")
    monkeypatch.setattr(settings, "ADMIN_ALLOWED_IPS", "203.0.113.0/24")
    body = {"name": "Network check"}

    outside = {**superuser_token_headers, "X-Forwarded-For": "198.51.100.7"}
    refused = client.post("/api/v1/order-status/", json=body, headers=outside)
    assert refused.status_code in (401, 403)

    inside = {**superuser_token_headers, "X-Forwarded-For": "203.0.113.20"}
    allowed = client.post("/api/v1/order-status/", json=body, headers=inside)
    assert allowed.status_code not in (401, 403)


def test_the_list_accepts_commas_and_a_typo_stops_the_start() -> None:
    from app.core.config import parse_admin_networks

    assert len(parse_admin_networks("203.0.113.0/24, 2001:db8::/32  10.0.0.1")) == 3
    assert parse_admin_networks(None) == []
    with pytest.raises(ValueError):
        parse_admin_networks("203.0.113.0/33")
