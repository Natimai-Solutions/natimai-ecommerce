from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse

from app.api.routes.payments import process_provider_webhook
from app.features.payment.services.provider_dispatch import (
    PaymentApiProviderResolutionError,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_payments_webhooks_payzen_delegates_to_payzen_ipn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    request = cast(
        Request,
        SimpleNamespace(form=AsyncMock(return_value={"kr-answer": "raw"})),
    )

    delegated_response = JSONResponse(content={"status": "ok", "message": "delegated"})

    async def _fake_payzen_ipn(*, session: object, request: object) -> JSONResponse:
        _ = (session, request)
        return delegated_response

    monkeypatch.setattr("app.api.routes.payments.payzen_ipn", _fake_payzen_ipn)

    response = await process_provider_webhook(
        provider_code="  PayZen  ",
        session=session,
        request=request,
    )

    assert response.status_code == 200
    assert response.body == delegated_response.body


@pytest.mark.anyio
async def test_payments_webhooks_unknown_provider_returns_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    request = cast(
        Request,
        SimpleNamespace(form=AsyncMock(return_value={})),
    )

    monkeypatch.setattr(
        "app.api.routes.payments.resolve_api_provider",
        Mock(side_effect=PaymentApiProviderResolutionError("Unknown payment provider: stripe")),
    )

    response = await process_provider_webhook(
        provider_code="stripe",
        session=session,
        request=request,
    )

    assert response.status_code == 404
    assert b"Unknown payment provider: stripe" in response.body


@pytest.mark.anyio
async def test_payments_webhooks_known_non_payzen_returns_501(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    request = cast(
        Request,
        SimpleNamespace(form=AsyncMock(return_value={})),
    )

    monkeypatch.setattr(
        "app.api.routes.payments.resolve_api_provider",
        Mock(return_value=cast(Any, object())),
    )

    response = await process_provider_webhook(
        provider_code="manual_check",
        session=session,
        request=request,
    )

    assert response.status_code == 501
    assert b"Webhook processing not implemented for provider: manual_check" in response.body
