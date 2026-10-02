"""Security headers of the API (R8 / U4): CSP on every JSON response, none on
the interactive docs, which load Swagger from a CDN."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_api_responses_carry_a_restrictive_csp() -> None:
    client = TestClient(app)
    response = client.get("/api/v1/healthz/liveness")
    assert response.status_code == 200
    csp = response.headers["content-security-policy"]
    assert "default-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_docs_pages_keep_their_own_policy() -> None:
    client = TestClient(app)
    response = client.get("/docs")
    # Docs are served outside production (the test settings are local).
    assert response.status_code == 200
    assert "content-security-policy" not in response.headers
