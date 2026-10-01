"""TOTP (RFC 6238) as authenticator apps compute it."""

import base64
from urllib.parse import parse_qs, urlsplit

from app.core import totp

# RFC 6238 appendix B, SHA-1 seed "12345678901234567890" (8-digit codes; the
# 6-digit code is their last six digits).
RFC_SECRET = base64.b32encode(b"12345678901234567890").decode()
RFC_VECTORS = {
    59: "94287082",
    1111111109: "07081804",
    1111111111: "14050471",
    1234567890: "89005924",
    2000000000: "69279037",
}


def test_rfc_6238_vectors() -> None:
    for at, expected in RFC_VECTORS.items():
        assert totp.code_at(RFC_SECRET, totp.current_step(at)) == expected[-6:]


def test_codes_match_within_one_step_of_drift_only() -> None:
    at = 1111111109.0
    step = totp.current_step(at)
    now_code = totp.code_at(RFC_SECRET, step)
    assert totp.matching_step(RFC_SECRET, now_code, at=at) == step
    assert totp.matching_step(RFC_SECRET, now_code, at=at + 30) == step
    assert totp.matching_step(RFC_SECRET, now_code, at=at - 30) == step
    assert totp.matching_step(RFC_SECRET, now_code, at=at + 90) is None
    # Spaces typed by the user are fine; a wrong length never matches.
    assert totp.matching_step(RFC_SECRET, f"{now_code[:3]} {now_code[3:]}", at=at)
    assert totp.matching_step(RFC_SECRET, "12345", at=at) is None


def test_generated_secret_and_provisioning_uri() -> None:
    secret = totp.generate_secret()
    assert len(secret) == 32
    uri = totp.provisioning_uri(secret, account="ops@shop.test", issuer="Shop admin")
    parts = urlsplit(uri)
    assert parts.scheme == "otpauth" and parts.netloc == "totp"
    query = parse_qs(parts.query)
    assert query["secret"] == [secret]
    assert query["issuer"] == ["Shop admin"]
    assert query["digits"] == ["6"] and query["period"] == ["30"]
