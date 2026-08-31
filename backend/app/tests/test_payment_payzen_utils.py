from typing import Any

import httpx
import pytest

from app.core.config import settings
from app.core.errors import AppError
from app.features.payment.utils.payzen import create_payzen_form_token


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = ""

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://payzen.test")
            response = httpx.Response(
                status_code=self.status_code,
                request=request,
                text=self.text,
            )
            raise httpx.HTTPStatusError(
                "status error",
                request=request,
                response=response,
            )


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_create_payzen_form_token_maps_gateway_error_to_app_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeClient:
        async def __aenter__(self) -> "_FakeClient":
            return self

        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
            return False

        async def post(self, *args: Any, **kwargs: Any) -> _FakeResponse:
            _ = (args, kwargs)
            return _FakeResponse(
                200,
                {
                    "status": "ERROR",
                    "answer": {
                        "errorCode": "INT_010",
                        "errorMessage": "Currency not supported",
                    },
                },
            )

    monkeypatch.setattr(
        "app.features.payment.utils.payzen.httpx.AsyncClient",
        _FakeClient,
    )

    with pytest.raises(AppError) as exc_info:
        await create_payzen_form_token(
            amount=1200,
            currency="XXX",
            order_id="order_123",
            customer_email="test@example.com",
            customer_reference="user_1",
        )

    assert exc_info.value.status_code == 502
    assert exc_info.value.code == "payment.provider.gateway_error"
    assert exc_info.value.details["provider_code"] == "payzen"
    assert exc_info.value.details["error_code"] == "INT_010"


@pytest.mark.anyio
async def test_create_payzen_form_token_maps_missing_form_token_to_app_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeClient:
        async def __aenter__(self) -> "_FakeClient":
            return self

        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
            return False

        async def post(self, *args: Any, **kwargs: Any) -> _FakeResponse:
            _ = (args, kwargs)
            return _FakeResponse(200, {"status": "SUCCESS", "answer": {}})

    monkeypatch.setattr(
        "app.features.payment.utils.payzen.httpx.AsyncClient",
        _FakeClient,
    )

    with pytest.raises(AppError) as exc_info:
        await create_payzen_form_token(
            amount=1200,
            currency="XPF",
            order_id="order_456",
            customer_email="test@example.com",
            customer_reference="user_1",
        )

    assert exc_info.value.status_code == 502
    assert exc_info.value.code == "payment.provider.invalid_response"
    assert exc_info.value.details == {
        "provider_code": "payzen",
        "reason": "missing_form_token",
    }


@pytest.mark.anyio
async def test_create_payzen_form_token_maps_request_error_to_service_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeClient:
        async def __aenter__(self) -> "_FakeClient":
            return self

        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
            return False

        async def post(self, *args: Any, **kwargs: Any) -> _FakeResponse:
            _ = (args, kwargs)
            request = httpx.Request("POST", "https://payzen.test")
            raise httpx.RequestError("network down", request=request)

    monkeypatch.setattr(
        "app.features.payment.utils.payzen.httpx.AsyncClient",
        _FakeClient,
    )

    with pytest.raises(AppError) as exc_info:
        await create_payzen_form_token(
            amount=1200,
            currency="XPF",
            order_id="order_789",
            customer_email="test@example.com",
            customer_reference="user_1",
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "internal.unavailable"
    assert exc_info.value.details == {"service": "payzen"}


# ---------------------------------------------------------------------------
# Chemin nominal et construction du payload (Q3)
# ---------------------------------------------------------------------------


def _capturing_client(
    payload_sink: dict[str, Any],
    response: _FakeResponse,
) -> type:
    """Faux client HTTP qui garde le corps envoyé à PayZen."""

    class _FakeClient:
        async def __aenter__(self) -> "_FakeClient":
            return self

        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
            return False

        async def post(self, *args: Any, **kwargs: Any) -> _FakeResponse:
            _ = args
            payload_sink.update(kwargs.get("json") or {})
            return response

    return _FakeClient


_SUCCESS = {"status": "SUCCESS", "answer": {"formToken": "tok_abc"}}


@pytest.mark.anyio
async def test_create_payzen_form_token_returns_the_token_and_test_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "PAYZEN_MODE", "TEST")
    monkeypatch.setattr(settings, "PAYZEN_PUBLIC_KEY_TEST", "pub_test")
    monkeypatch.setattr(settings, "PAYZEN_PUBLIC_KEY_PROD", "pub_prod")
    sent: dict[str, Any] = {}
    monkeypatch.setattr(
        "app.features.payment.utils.payzen.httpx.AsyncClient",
        _capturing_client(sent, _FakeResponse(200, _SUCCESS)),
    )

    result = await create_payzen_form_token(
        amount=1200,
        currency="XPF",
        order_id="order_ok",
        customer_email="test@example.com",
        customer_reference="user_1",
    )

    assert result["form_token"] == "tok_abc"
    assert result["public_key"] == "pub_test"
    assert result["server_url"] == settings.PAYZEN_STATIC_URL
    assert result["raw_response"] == {"formToken": "tok_abc"}
    assert sent["amount"] == 1200
    assert sent["currency"] == "XPF"
    assert sent["customer"]["email"] == "test@example.com"
    # Débit immédiat par défaut : pas d'autorisation seule sans le demander.
    assert "manualValidation" not in sent


@pytest.mark.anyio
async def test_production_mode_returns_the_production_public_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Servir la clé de test en production ferait échouer tous les paiements."""
    monkeypatch.setattr(settings, "PAYZEN_MODE", "PRODUCTION")
    monkeypatch.setattr(settings, "PAYZEN_PUBLIC_KEY_TEST", "pub_test")
    monkeypatch.setattr(settings, "PAYZEN_PUBLIC_KEY_PROD", "pub_prod")
    monkeypatch.setattr(
        "app.features.payment.utils.payzen.httpx.AsyncClient",
        _capturing_client({}, _FakeResponse(200, _SUCCESS)),
    )

    result = await create_payzen_form_token(
        amount=1200,
        currency="XPF",
        order_id="order_prod",
        customer_email="test@example.com",
        customer_reference="user_1",
    )

    assert result["public_key"] == "pub_prod"


@pytest.mark.anyio
async def test_manual_validation_asks_payzen_to_authorise_without_debiting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Capture différée (débit à l'expédition) : le flag part bien à la passerelle."""
    sent: dict[str, Any] = {}
    monkeypatch.setattr(
        "app.features.payment.utils.payzen.httpx.AsyncClient",
        _capturing_client(sent, _FakeResponse(200, _SUCCESS)),
    )

    await create_payzen_form_token(
        amount=1200,
        currency="XPF",
        order_id="order_auth",
        customer_email="test@example.com",
        customer_reference="user_1",
        manual_validation=True,
    )

    assert sent["manualValidation"] == "YES"


@pytest.mark.anyio
async def test_metadata_and_explicit_return_url_are_forwarded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: dict[str, Any] = {}
    monkeypatch.setattr(
        "app.features.payment.utils.payzen.httpx.AsyncClient",
        _capturing_client(sent, _FakeResponse(200, _SUCCESS)),
    )

    await create_payzen_form_token(
        amount=1200,
        currency="XPF",
        order_id="order_meta",
        customer_email="test@example.com",
        customer_reference="user_1",
        return_url="https://shop.test/retour",
        metadata={"payment_id": "p1"},
    )

    assert sent["metadata"] == {"payment_id": "p1"}
    assert sent["contrib"] == "https://shop.test/retour"


@pytest.mark.anyio
async def test_configured_return_url_is_used_when_the_caller_gives_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "PAYZEN_RETURN_URL", "https://shop.test/defaut")
    sent: dict[str, Any] = {}
    monkeypatch.setattr(
        "app.features.payment.utils.payzen.httpx.AsyncClient",
        _capturing_client(sent, _FakeResponse(200, _SUCCESS)),
    )

    await create_payzen_form_token(
        amount=1200,
        currency="XPF",
        order_id="order_default_url",
        customer_email="test@example.com",
        customer_reference="user_1",
    )

    assert sent["contrib"] == "https://shop.test/defaut"


# ---------------------------------------------------------------------------
# Mapping des erreurs restantes (Q3)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_non_json_response_is_reported_as_an_invalid_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Une page HTML d'erreur ne doit pas ressortir en 500 anonyme."""

    class _HtmlResponse(_FakeResponse):
        def json(self) -> dict[str, Any]:
            raise ValueError("not json")

    monkeypatch.setattr(
        "app.features.payment.utils.payzen.httpx.AsyncClient",
        _capturing_client({}, _HtmlResponse(200, {})),
    )

    with pytest.raises(AppError) as exc_info:
        await create_payzen_form_token(
            amount=1200,
            currency="XPF",
            order_id="order_html",
            customer_email="test@example.com",
            customer_reference="user_1",
        )

    assert exc_info.value.status_code == 502
    assert exc_info.value.code == "payment.provider.invalid_response"
    assert exc_info.value.details["reason"] == "invalid_json"


@pytest.mark.anyio
async def test_missing_acceptance_contract_names_the_currency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PSP_610 : contrat d'acceptation absent pour cette devise, pas une panne."""
    monkeypatch.setattr(
        "app.features.payment.utils.payzen.httpx.AsyncClient",
        _capturing_client(
            {},
            _FakeResponse(
                200,
                {
                    "status": "ERROR",
                    "answer": {"errorCode": "PSP_610", "errorMessage": "no contract"},
                },
            ),
        ),
    )

    with pytest.raises(AppError) as exc_info:
        await create_payzen_form_token(
            amount=1200,
            currency="EUR",
            order_id="order_psp610",
            customer_email="test@example.com",
            customer_reference="user_1",
        )

    assert exc_info.value.status_code == 502
    assert "EUR" in exc_info.value.message
    assert exc_info.value.details["error_code"] == "PSP_610"


@pytest.mark.anyio
async def test_unknown_error_code_falls_back_to_the_detailed_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.features.payment.utils.payzen.httpx.AsyncClient",
        _capturing_client(
            {},
            _FakeResponse(
                200,
                {
                    "status": "ERROR",
                    "answer": {
                        "errorCode": "PSP_999",
                        "errorMessage": "générique",
                        "detailedErrorMessage": "carte refusée par l'émetteur",
                    },
                },
            ),
        ),
    )

    with pytest.raises(AppError) as exc_info:
        await create_payzen_form_token(
            amount=1200,
            currency="XPF",
            order_id="order_unknown",
            customer_email="test@example.com",
            customer_reference="user_1",
        )

    assert exc_info.value.message == "carte refusée par l'émetteur"


@pytest.mark.anyio
async def test_http_error_status_is_mapped_to_service_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.features.payment.utils.payzen.httpx.AsyncClient",
        _capturing_client({}, _FakeResponse(503, {"status": "SUCCESS", "answer": {}})),
    )

    with pytest.raises(AppError) as exc_info:
        await create_payzen_form_token(
            amount=1200,
            currency="XPF",
            order_id="order_503",
            customer_email="test@example.com",
            customer_reference="user_1",
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "internal.unavailable"
    assert exc_info.value.details == {"service": "payzen", "status_code": 503}


@pytest.mark.anyio
async def test_unexpected_error_keeps_its_type_in_the_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le type d'exception est la seule piste laissée au diagnostic."""

    class _BoomClient:
        async def __aenter__(self) -> "_BoomClient":
            return self

        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
            return False

        async def post(self, *args: Any, **kwargs: Any) -> None:
            _ = (args, kwargs)
            raise RuntimeError("boom")

    monkeypatch.setattr(
        "app.features.payment.utils.payzen.httpx.AsyncClient", _BoomClient
    )

    with pytest.raises(AppError) as exc_info:
        await create_payzen_form_token(
            amount=1200,
            currency="XPF",
            order_id="order_boom",
            customer_email="test@example.com",
            customer_reference="user_1",
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.code == "payment.provider.gateway_error"
    assert exc_info.value.details == {
        "provider_code": "payzen",
        "reason": "RuntimeError",
    }
