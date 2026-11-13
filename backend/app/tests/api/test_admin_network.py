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
