from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.features.base.crud import RecordNotFoundError

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Application error with stable machine-readable code."""

    def __init__(
        self,
        *,
        code: str,
        status_code: int = 400,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        resolved_message = message or code
        super().__init__(resolved_message)
        self.code = code
        self.status_code = status_code
        self.message = resolved_message
        self.details = details or {}


def _app_error_payload(exc: AppError) -> dict[str, Any]:
    """Build the standardized API payload for application errors."""
    return {
        "error": {
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
        }
    }


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    """Handle application errors with a stable payload contract."""
    return JSONResponse(status_code=exc.status_code, content=_app_error_payload(exc))


async def record_not_found_handler(
    _request: Request, exc: RecordNotFoundError
) -> JSONResponse:
    """Map uncaught not-found CRUD errors to stable API error codes."""
    error = AppError(
        code="internal.record_not_found",
        status_code=404,
        message=str(exc),
        details={},
    )
    return JSONResponse(status_code=error.status_code, content=_app_error_payload(error))


async def unexpected_exception_handler(
    _request: Request, exc: Exception
) -> JSONResponse:
    """Hide sensitive details for unexpected 500 responses in non-local envs."""
    logger.exception("Unhandled server exception", exc_info=exc)

    if settings.ENVIRONMENT == "local":
        message = str(exc).strip() or type(exc).__name__
        debug_error = AppError(
            code="internal.server_error",
            status_code=500,
            message=message,
            details={"exception_type": type(exc).__name__},
        )
        return JSONResponse(
            status_code=debug_error.status_code,
            content=_app_error_payload(debug_error),
        )

    return JSONResponse(
        status_code=500,
        content={"error": {"code": "internal.server_error"}},
    )


def register_error_handlers(app: FastAPI) -> None:
    """Register all API-wide exception handlers."""
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RecordNotFoundError, record_not_found_handler)
    app.add_exception_handler(Exception, unexpected_exception_handler)
