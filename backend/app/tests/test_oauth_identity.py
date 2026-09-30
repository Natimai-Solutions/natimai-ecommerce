"""Which e-mails a social provider really vouches for (nOAuth, 30/09/2026)."""

from __future__ import annotations

import base64
import json
from typing import Any

import pytest

from app.api.routes.oauth import (
    _extract_user_info,
    _id_token_claims,
    _microsoft_email_verified,
)
from app.core.config import settings

MSA_TENANT = "9188040d-6c67-4c5b-b112-36a304b66dad"
SHOP_TENANT = "11111111-2222-3333-4444-555555555555"
OTHER_TENANT = "99999999-8888-7777-6666-555555555555"


def _id_token(claims: dict[str, Any]) -> str:
    def part(data: dict[str, Any]) -> str:
        raw = json.dumps(data).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    return f"{part({'alg': 'RS256'})}.{part(claims)}.signature"


def test_id_token_claims_are_read_without_padding() -> None:
    token = _id_token({"tid": SHOP_TENANT, "email": "a@b.c"})
    assert _id_token_claims({"id_token": token})["tid"] == SHOP_TENANT


@pytest.mark.parametrize("token", [None, "", "not-a-jwt", "a.%%%.c", 42])
def test_malformed_id_token_gives_no_claims(token: object) -> None:
    assert _id_token_claims({"id_token": token}) == {}


@pytest.mark.parametrize(
    ("flag", "verified"),
    [(True, True), ("true", True), (False, False), (None, False), ("yes", False)],
)
def test_google_trusts_only_email_verified(flag: object, verified: bool) -> None:
    info: dict[str, object] = {
        "sub": "g-1",
        "email": " Someone@Example.COM ",
        "name": "S",
    }
    if flag is not None:
        info["email_verified"] = flag
    identity = _extract_user_info("google", info, {})
    assert identity.email == "someone@example.com"
    assert identity.email_verified is verified


@pytest.mark.parametrize(
    ("configured", "claims", "verified"),
    [
        # Multi-tenant app (default): only personal accounts or xms_edov.
        ("common", {"tid": MSA_TENANT}, True),
        ("common", {"tid": OTHER_TENANT}, False),
        ("common", {}, False),
        ("organizations", {"tid": OTHER_TENANT}, False),
        ("common", {"tid": OTHER_TENANT, "xms_edov": True}, True),
        ("common", {"tid": OTHER_TENANT, "xms_edov": "1"}, True),
        # Single-tenant app: the shop's own directory.
        (SHOP_TENANT, {"tid": SHOP_TENANT}, True),
        (SHOP_TENANT.upper(), {"tid": SHOP_TENANT}, True),
        (SHOP_TENANT, {"tid": OTHER_TENANT}, False),
        ("natimai.onmicrosoft.com", {"tid": SHOP_TENANT}, True),
    ],
)
def test_microsoft_email_verification(
    monkeypatch: pytest.MonkeyPatch,
    configured: str,
    claims: dict[str, Any],
    verified: bool,
) -> None:
    monkeypatch.setattr(settings, "MICROSOFT_TENANT_ID", configured)
    assert _microsoft_email_verified(claims) is verified


def test_microsoft_identity_prefers_mail_then_upn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "MICROSOFT_TENANT_ID", "common")
    identity = _extract_user_info(
        "microsoft",
        {"id": "m-1", "userPrincipalName": "Person@Outlook.com", "displayName": "P"},
        {"tid": MSA_TENANT},
    )
    assert identity.email == "person@outlook.com"
    assert identity.email_verified is True
