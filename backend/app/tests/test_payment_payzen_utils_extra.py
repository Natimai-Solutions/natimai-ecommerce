"""PayZen (Q3) — les branches de ``utils/payzen.py`` que les tests existants
ne traversaient pas : composition du payload (validation manuelle, métadonnées,
URL de retour), messages d'aide par code d'erreur, réponse illisible, erreur
HTTP, exception inattendue, et l'appel de capture ``Transaction/Validate``.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.core.config import settings
from app.core.errors import AppError
from app.features.payment.utils.payzen import (
    capture_payzen_transaction,
    create_payzen_form_token,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class _Response:
    def __init__(
        self, status_code: int = 200, payload: Any = None, *, invalid_json: bool = False
    ) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self._invalid_json = invalid_json
        self.text = "body"

    def json(self) -> Any:
        if self._invalid_json:
            raise ValueError("not json")
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://payzen.test")
            raise httpx.HTTPStatusError(
                "status error",
                request=request,
                response=httpx.Response(
                    self.status_code, request=request, text=self.text
                ),
            )


def _client(monkeypatch: pytest.MonkeyPatch, handler: Any) -> list[dict[str, Any]]:
    """Remplace httpx.AsyncClient par un faux dont ``post`` appelle ``handler``
    et journalise les appels (url, json, headers)."""
    calls: list[dict[str, Any]] = []

    class _FakeClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            _ = (args, kwargs)

        async def __aenter__(self) -> _FakeClient:
            return self

        async def __aexit__(self, *exc: Any) -> bool:
            return False

        async def post(self, url: str, **kwargs: Any) -> Any:
            calls.append({"url": url, **kwargs})
            return handler()

    monkeypatch.setattr(
        "app.features.payment.utils.payzen.httpx.AsyncClient", _FakeClient
    )
    return calls


def _ok_token() -> _Response:
    return _Response(200, {"status": "SUCCESS", "answer": {"formToken": "tok_123"}})


async def _create(**overrides: Any) -> dict[str, Any]:
    params: dict[str, Any] = {
        "amount": 1500,
        "currency": "XPF",
        "order_id": "CMD-2026-00001",
        "customer_email": "client@example.pf",
        "customer_reference": "user_1",
    }
    params.update(overrides)
    return await create_payzen_form_token(**params)


@pytest.mark.anyio
async def test_success_returns_the_token_and_the_test_public_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "PAYZEN_MODE", "TEST")
    monkeypatch.setattr(settings, "PAYZEN_PUBLIC_KEY_TEST", "pk_test")
    monkeypatch.setattr(settings, "PAYZEN_PUBLIC_KEY_PROD", "pk_prod")
    calls = _client(monkeypatch, _ok_token)

    result = await _create()

    assert result["form_token"] == "tok_123"
    assert result["public_key"] == "pk_test"
    assert result["server_url"] == settings.PAYZEN_STATIC_URL
    assert calls[0]["url"].endswith("/api-payment/V4/Charge/CreatePayment")
    assert calls[0]["headers"]["Authorization"].startswith("Basic ")


@pytest.mark.anyio
async def test_payload_carries_manual_validation_metadata_and_return_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La capture différée (autorisation au checkout, débit à l'expédition)
    repose sur ``manualValidation: YES`` — s'il manque, le client est débité
    tout de suite."""
    monkeypatch.setattr(settings, "PAYZEN_RETURN_URL", "https://shop.example/retour")
    calls = _client(monkeypatch, _ok_token)

    await _create(
        manual_validation=True,
        metadata={"order_number": "CMD-2026-00001"},
        return_url="https://shop.example/merci",
    )
    body = calls[0]["json"]
    assert body["manualValidation"] == "YES"
    assert body["metadata"] == {"order_number": "CMD-2026-00001"}
    assert body["contrib"] == "https://shop.example/merci"  # explicite > réglage

    await _create()
    body = calls[1]["json"]
    assert "manualValidation" not in body
    assert "metadata" not in body
    assert body["contrib"] == "https://shop.example/retour"  # repli sur le réglage


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("error_code", "expected_fragment"),
    [
        ("INT_010", "Currency XPF is not supported"),
        ("PSP_610", "No acceptance contract for currency XPF"),
        ("AUTRE", "Explication détaillée"),
    ],
)
async def test_gateway_errors_carry_an_actionable_message(
    monkeypatch: pytest.MonkeyPatch, error_code: str, expected_fragment: str
) -> None:
    _client(
        monkeypatch,
        lambda: _Response(
            200,
            {
                "status": "ERROR",
                "answer": {
                    "errorCode": error_code,
                    "errorMessage": "Message court",
                    "detailedErrorMessage": "Explication détaillée",
                },
            },
        ),
    )

    with pytest.raises(AppError) as exc:
        await _create()

    assert exc.value.status_code == 502
    assert exc.value.code == "payment.provider.gateway_error"
    assert expected_fragment in exc.value.message
    assert exc.value.details["error_code"] == error_code


@pytest.mark.anyio
async def test_an_unreadable_response_is_a_502_not_a_500(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _client(monkeypatch, lambda: _Response(200, invalid_json=True))

    with pytest.raises(AppError) as exc:
        await _create()

    assert exc.value.status_code == 502
    assert exc.value.code == "payment.provider.invalid_response"
    assert exc.value.details["reason"] == "invalid_json"


@pytest.mark.anyio
async def test_an_http_error_status_is_a_503(monkeypatch: pytest.MonkeyPatch) -> None:
    _client(monkeypatch, lambda: _Response(500, {"status": "SUCCESS"}))

    with pytest.raises(AppError) as exc:
        await _create()

    assert exc.value.status_code == 503
    assert exc.value.code == "internal.unavailable"
    assert exc.value.details["status_code"] == 500


@pytest.mark.anyio
async def test_an_unexpected_exception_is_wrapped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom() -> Any:
        raise RuntimeError("kaboom")

    _client(monkeypatch, boom)

    with pytest.raises(AppError) as exc:
        await _create()

    assert exc.value.status_code == 500
    assert exc.value.details["reason"] == "RuntimeError"


# ---------------------------------------------------------------------------
# Capture (Transaction/Validate)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_capture_posts_the_transaction_uuid_and_returns_the_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _client(
        monkeypatch,
        lambda: _Response(
            200, {"status": "SUCCESS", "answer": {"detailedStatus": "CAPTURED"}}
        ),
    )

    answer = await capture_payzen_transaction("trs-uuid-1")

    assert answer == {"detailedStatus": "CAPTURED"}
    assert calls[0]["url"].endswith("/api-payment/V4/Transaction/Validate")
    assert calls[0]["json"] == {"uuid": "trs-uuid-1"}


@pytest.mark.anyio
async def test_capture_gateway_error_is_a_502(monkeypatch: pytest.MonkeyPatch) -> None:
    _client(
        monkeypatch,
        lambda: _Response(
            200,
            {
                "status": "ERROR",
                "answer": {"errorCode": "PSP_099", "errorMessage": "Already captured"},
            },
        ),
    )

    with pytest.raises(AppError) as exc:
        await capture_payzen_transaction("trs-uuid-2")

    assert exc.value.status_code == 502
    assert exc.value.message == "Already captured"
    assert exc.value.details["error_code"] == "PSP_099"


@pytest.mark.anyio
async def test_capture_transport_errors_are_a_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def down() -> Any:
        raise httpx.RequestError(
            "network down", request=httpx.Request("POST", "https://payzen.test")
        )

    _client(monkeypatch, down)
    with pytest.raises(AppError) as exc:
        await capture_payzen_transaction("trs-uuid-3")
    assert exc.value.status_code == 503

    _client(monkeypatch, lambda: _Response(502, {"status": "SUCCESS"}))
    with pytest.raises(AppError) as exc:
        await capture_payzen_transaction("trs-uuid-4")
    assert exc.value.status_code == 503
