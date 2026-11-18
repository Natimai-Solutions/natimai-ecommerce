from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.features.base.crud import RecordNotFoundError

logger = logging.getLogger(__name__)


_PLACEHOLDER = re.compile(r"\{([a-z_][a-z0-9_]*)\}")


def fill_placeholders(message: str, details: dict[str, Any]) -> str:
    """``{name}`` replaced by ``details[name]`` when it is there.

    The fallback message is the English text of the shared catalogue
    (``shared/utils/src/apiErrors/en.json``), placeholders included: the same
    values fill it here and in the frontends.
    """
    return _PLACEHOLDER.sub(
        lambda m: str(details[m.group(1)]) if m.group(1) in details else m.group(0),
        message,
    )


class AppError(Exception):
    """Application error with a stable machine-readable code.

    The API is language-agnostic: clients translate the ``code`` (with the
    ``details`` as parameters) — the frontends from the shared catalogue
    ``shared/utils/src/apiErrors/{en,fr}.json``. ``message`` is the English
    fallback, the catalogue's English text, for API clients and logs.
    """

    def __init__(
        self,
        *,
        code: str,
        status_code: int = 400,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.details = details or {}
        resolved_message = fill_placeholders(message or code, self.details)
        super().__init__(resolved_message)
        self.code = code
        self.status_code = status_code
        self.message = resolved_message


def _app_error_payload(exc: AppError) -> dict[str, Any]:
    """Build the standardized API payload for application errors."""
    return {
        "error": {
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
        }
    }


async def app_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Handle application errors with a stable payload contract: the code,
    its English fallback message, its details. The client translates."""
    assert isinstance(exc, AppError)
    return JSONResponse(status_code=exc.status_code, content=_app_error_payload(exc))


async def record_not_found_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Map uncaught not-found CRUD errors to stable API error codes."""
    assert isinstance(exc, RecordNotFoundError)
    error = AppError(
        code="internal.record_not_found",
        status_code=404,
        message=str(exc),
        details={},
    )
    return JSONResponse(
        status_code=error.status_code, content=_app_error_payload(error)
    )


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


class PriceUnavailableError(Exception):
    """A price that cannot be computed (the pricing layer's
    ``CurrencyRateMissing`` derives from it, so this module imports nothing
    from the features)."""


async def currency_rate_missing_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """A price that cannot be computed is a product not on sale, not a crash."""
    logger.warning("Price not computable: %s", exc)
    error = AppError(
        code="product.price_unavailable",
        status_code=409,
        message="The price of this item is not available at the moment.",
        details={"currency": getattr(exc, "currency_code", None)},
    )
    # Through the common handler (same payload contract).
    return await app_error_handler(request, error)


def register_error_handlers(app: FastAPI) -> None:
    """Register all API-wide exception handlers."""
    app.add_exception_handler(PriceUnavailableError, currency_rate_missing_handler)
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RecordNotFoundError, record_not_found_handler)
    app.add_exception_handler(Exception, unexpected_exception_handler)
