from typing import Any

import httpx
import pytest

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
