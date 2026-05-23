from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.core.errors import AppError, register_error_handlers
from app.features.base.crud import RecordNotFoundError


def _build_test_app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/app-error")
    async def raise_app_error() -> None:
        raise AppError(
            code="payment.not_manual",
            status_code=400,
            message="Payment provider 'payzen' is not manual",
            details={"provider_code": "payzen", "payment_id": "demo"},
        )

    @app.get("/record-not-found")
    async def raise_record_not_found() -> None:
        raise RecordNotFoundError("The record doesn't exist.")

    @app.get("/boom")
    async def raise_unexpected_error() -> None:
        raise RuntimeError("boom")

    @app.get("/http-exception")
    async def raise_http_exception() -> None:
        raise HTTPException(status_code=418, detail="teapot")

    @app.get("/items/{item_id}")
    async def read_item(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}

    return app


@pytest.mark.asyncio
async def test_app_error_payload_contract() -> None:
    app = _build_test_app()
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get("/app-error")

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "payment.not_manual",
            "message": "Payment provider 'payzen' is not manual",
            "details": {"provider_code": "payzen", "payment_id": "demo"},
        }
    }


@pytest.mark.asyncio
async def test_record_not_found_is_mapped() -> None:
    app = _build_test_app()
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get("/record-not-found")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "internal.record_not_found",
            "message": "The record doesn't exist.",
            "details": {},
        }
    }


@pytest.mark.asyncio
async def test_unexpected_error_payload_is_minimal_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    app = _build_test_app()

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get("/boom")

    assert response.status_code == 500
    assert response.json() == {"error": {"code": "internal.server_error"}}


@pytest.mark.asyncio
async def test_unexpected_error_payload_is_debug_in_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ENVIRONMENT", "local")
    app = _build_test_app()

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get("/boom")

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "internal.server_error",
            "message": "boom",
            "details": {"exception_type": "RuntimeError"},
        }
    }


@pytest.mark.asyncio
async def test_http_exception_and_422_keep_fastapi_default_payload() -> None:
    app = _build_test_app()
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        http_response = await client.get("/http-exception")
        validation_response = await client.get("/items/not-an-int")

    assert http_response.status_code == 418
    assert http_response.json() == {"detail": "teapot"}

    assert validation_response.status_code == 422
    assert "detail" in validation_response.json()
