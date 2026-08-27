"""PayZen IPN signature validation and REST helpers (Q3).

`validate_ipn_signature` is the boundary that decides whether an inbound
notification really comes from PayZen. Everywhere else in the suite it is
mocked out — so the HMAC comparison that stops a forged "your order is paid"
callback was never actually executed by a test. These exercise it for real.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

import pytest

from app.core.config import settings
from app.core.errors import AppError
from app.features.payment.utils.payzen import (
    _payzen_basic_auth,
    capture_payzen_transaction,
    validate_ipn_signature,
)

_HMAC_KEY = "test-hmac-key"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _payzen_test_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "PAYZEN_MODE", "TEST")
    monkeypatch.setattr(settings, "PAYZEN_API_PASSWORD_TEST", _HMAC_KEY)
    monkeypatch.setattr(settings, "PAYZEN_API_PASSWORD_PROD", "prod-key")
    monkeypatch.setattr(settings, "PAYZEN_SITE_ID", "12345678")


def _answer(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "orderStatus": "PAID",
        "orderDetails": {"orderId": "order-42"},
        "transactions": [
            {
                "uuid": "trans-uuid-1",
                "amount": 119000,
                "currency": "953",
                "status": "PAID",
                "errorCode": None,
                "errorMessage": None,
                "transactionDetails": {"cardDetails": {"brand": "VISA"}},
            }
        ],
    }
    payload.update(overrides)
    return payload


def _signed(answer: dict[str, Any], *, key: str = _HMAC_KEY) -> dict[str, Any]:
    """An IPN payload signed the way PayZen signs it: hex HMAC-SHA256."""
    kr_answer = json.dumps(answer)
    kr_hash = hmac.new(
        key.encode("utf-8"), kr_answer.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return {
        "kr-answer": kr_answer,
        "kr-hash": kr_hash,
        "kr-hash-algorithm": "sha256_hmac",
    }


def test_valid_signature_extracts_the_payment_fields() -> None:
    result = validate_ipn_signature(_signed(_answer()))

    assert result["order_id"] == "order-42"
    assert result["trans_uuid"] == "trans-uuid-1"
    assert result["amount"] == "119000"
    assert result["currency"] == "953"  # XPF
    assert result["trans_status"] == "PAID"
    assert result["order_status"] == "PAID"
    assert result["payment_cards"] == "VISA"


def test_a_tampered_amount_is_rejected() -> None:
    """The attack this function exists to stop: replay a real IPN with the
    amount rewritten, so a 1 XPF payment marks a 500 000 XPF order paid."""
    fields = _signed(_answer())
    tampered = json.loads(fields["kr-answer"])
    tampered["transactions"][0]["amount"] = 1
    fields["kr-answer"] = json.dumps(tampered)  # signature left untouched

    with pytest.raises(ValueError, match="Invalid IPN signature"):
        validate_ipn_signature(fields)


def test_a_signature_from_another_key_is_rejected() -> None:
    with pytest.raises(ValueError, match="Invalid IPN signature"):
        validate_ipn_signature(_signed(_answer(), key="attacker-key"))


def test_missing_fields_are_rejected() -> None:
    fields = _signed(_answer())

    with pytest.raises(ValueError, match="kr-hash"):
        validate_ipn_signature({k: v for k, v in fields.items() if k != "kr-hash"})

    with pytest.raises(ValueError, match="kr-answer"):
        validate_ipn_signature({k: v for k, v in fields.items() if k != "kr-answer"})


def test_an_unconfigured_key_refuses_rather_than_accepts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing HMAC key must never degrade into "accept everything"."""
    monkeypatch.setattr(settings, "PAYZEN_API_PASSWORD_TEST", None)

    with pytest.raises(ValueError, match="not configured"):
        validate_ipn_signature(_signed(_answer()))


def test_a_correctly_signed_but_unusable_answer_is_rejected() -> None:
    # Valid signature over non-JSON.
    kr_answer = "not json at all"
    kr_hash = hmac.new(
        _HMAC_KEY.encode("utf-8"), kr_answer.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    with pytest.raises(ValueError, match="not valid JSON"):
        validate_ipn_signature({"kr-answer": kr_answer, "kr-hash": kr_hash})

    # Valid signature, valid JSON, but no transaction to act on.
    with pytest.raises(ValueError, match="No transaction"):
        validate_ipn_signature(_signed(_answer(transactions=[])))


def test_production_mode_uses_the_production_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Signing with the test key must not validate against production."""
    monkeypatch.setattr(settings, "PAYZEN_MODE", "PRODUCTION")

    with pytest.raises(ValueError, match="Invalid IPN signature"):
        validate_ipn_signature(_signed(_answer(), key=_HMAC_KEY))

    assert validate_ipn_signature(_signed(_answer(), key="prod-key"))


def test_basic_auth_follows_the_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    import base64

    assert base64.b64decode(_payzen_basic_auth()).decode() == f"12345678:{_HMAC_KEY}"

    monkeypatch.setattr(settings, "PAYZEN_MODE", "PRODUCTION")
    assert base64.b64decode(_payzen_basic_auth()).decode() == "12345678:prod-key"


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        return None


class _FakeClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def post(self, *_: object, **__: object) -> _FakeResponse:
        return _FakeResponse(self._payload)


@pytest.mark.anyio
async def test_capture_returns_the_gateway_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.features.payment.utils.payzen.httpx.AsyncClient",
        lambda *a, **k: _FakeClient({"status": "SUCCESS", "answer": {"uuid": "t-1"}}),
    )

    assert await capture_payzen_transaction("t-1") == {"uuid": "t-1"}


@pytest.mark.anyio
async def test_a_gateway_refusal_surfaces_as_a_typed_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The caller marks the capture failed on AppError; a bare exception would
    leave the payment in limbo."""
    monkeypatch.setattr(
        "app.features.payment.utils.payzen.httpx.AsyncClient",
        lambda *a, **k: _FakeClient(
            {
                "status": "ERROR",
                "answer": {"errorCode": "PSP_010", "errorMessage": "Refusé"},
            }
        ),
    )

    with pytest.raises(AppError) as exc:
        await capture_payzen_transaction("t-1")

    assert exc.value.status_code == 502
    assert exc.value.code == "payment.provider.gateway_error"
    assert exc.value.details["error_code"] == "PSP_010"


@pytest.mark.anyio
async def test_a_transport_failure_is_reported_as_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    class _Failing(_FakeClient):
        async def post(self, *_: object, **__: object) -> _FakeResponse:
            raise httpx.ConnectError("no route to host")

    monkeypatch.setattr(
        "app.features.payment.utils.payzen.httpx.AsyncClient",
        lambda *a, **k: _Failing({}),
    )

    with pytest.raises(AppError) as exc:
        await capture_payzen_transaction("t-1")

    # 503, not 502: the gateway did not refuse — we never reached it, so a
    # retry is meaningful.
    assert exc.value.status_code == 503
    assert exc.value.code == "internal.unavailable"
