import logging
import time
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.routing import APIRoute
from starlette.middleware.cors import CORSMiddleware

from app.api import api_router
from app.core import security
from app.core.config import settings
from app.core.errors import register_error_handlers
from app.core.logging_config import configure_logging
from app.core.metrics import http_metrics
from app.core.rate_limit import get_client_ip
from app.core.sentry import init_sentry
from app.features.system import audit
from app.outbox.loader import load_handlers


def custom_generate_unique_id(route: APIRoute) -> str:
    """Execute custom generate unique id."""
    return f"{route.tags[0]}-{route.name}"


configure_logging(service="api")
init_sentry("api")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Load the outbox handlers at start-up; log the shutdown."""
    load_handlers()
    from app.outbox.registry import outbox_registry

    logger.info(
        "Outbox handlers registered",
        extra={"handlers": sorted(outbox_registry.handlers.keys())},
    )

    yield

    logger.info("Shutting down")


app = FastAPI(
    title=settings.PROJECT_NAME,
    # No /docs, /redoc nor openapi.json in production: the schema documents
    # the whole attack surface. They stay available in local/staging (the
    # api-types generator reads openapi.json from a local instance).
    openapi_url=(
        None
        if settings.ENVIRONMENT == "production"
        else f"{settings.API_V1_STR}/openapi.json"
    ),
    generate_unique_id_function=custom_generate_unique_id,
    lifespan=lifespan,
)

register_error_handlers(app)


@app.middleware("http")
async def request_locale_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Language of the request (``Accept-Language``), for the code that sends
    e-mails or freezes the order's language (R7 / L3)."""
    from app.core.i18n import (
        from_accept_language,
        reset_request_locale,
        set_request_locale,
    )

    token = set_request_locale(
        from_accept_language(request.headers.get("accept-language"))
    )
    try:
        return await call_next(request)
    finally:
        reset_request_locale(token)


@app.middleware("http")
async def security_headers_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Baseline security headers on every response.

    HSTS is only meaningful over HTTPS, hence gated on non-local (TLS is
    terminated by Cloudflare / the reverse proxy in staging & production).
    """
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    # A JSON API renders nothing: a page served from it (an error page, an
    # uploaded file echoed back) can load no script and be framed nowhere
    # (R8 / U4). The interactive docs (local / staging) load Swagger from a
    # CDN and keep their own policy.
    if not request.url.path.startswith(_DOCS_PATHS):
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; "
            "form-action 'none'",
        )
    if settings.ENVIRONMENT != "local":
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response


#: Paths whose HTML loads Swagger / ReDoc from a CDN: no API CSP on them.
_DOCS_PATHS = ("/docs", "/redoc", f"{settings.API_V1_STR}/openapi.json")


@app.middleware("http")
async def admin_audit_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Journal every state-changing request made by an administrator (R6).

    Only POST / PUT / PATCH / DELETE under the API carrying a bearer token
    are looked at; the author is resolved after the response, and only a
    superuser's request is written (no body: see ``AdminAuditEntry``). The
    sign-in itself is journaled by the login route.
    """
    method = request.method.upper()
    path = request.url.path
    authorization = request.headers.get("authorization", "")
    if (
        method not in audit.MUTATING_METHODS
        or not path.startswith(settings.API_V1_STR)
        or path.startswith(f"{settings.API_V1_STR}/login/")
        or not authorization.lower().startswith("bearer ")
    ):
        return await call_next(request)
    try:
        payload = security.decode_token(authorization.split(" ", 1)[1].strip())
        user_id = uuid.UUID(str(payload.get("sub")))
        if payload.get("type") not in (None, "access"):
            raise ValueError("not an access token")
    except Exception:  # noqa: BLE001 - not ours to judge: the route will
        return await call_next(request)
    response = await call_next(request)
    # The matched route's template, relative to the API router it lives in.
    template = getattr(request.scope.get("route"), "path", None)
    if template and not template.startswith(settings.API_V1_STR):
        template = f"{settings.API_V1_STR}{template}"
    await audit.record_admin_request(
        user_id=user_id,
        method=method,
        path=path,
        route=template,
        status_code=response.status_code,
        path_params=dict(request.path_params),
        query=dict(request.query_params),
        ip=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return response


# Set all CORS enabled origins.
#
# Driven by ``all_cors_origins`` (BACKEND_CORS_ORIGINS + FRONTEND_HOST), not by
# BACKEND_CORS_ORIGINS alone. The storefront and the API live on different
# subdomains in production, so every browser call is cross-origin: gating the
# middleware on BACKEND_CORS_ORIGINS meant that setting only FRONTEND_HOST —
# which the deployment guide describes as the CORS origin — left the middleware
# uninstalled and the storefront unable to reach the API at all.
if settings.all_cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.all_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router, prefix=settings.API_V1_STR)


@app.middleware("http")
async def http_metrics_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Count and time every request for ``GET /metrics`` (R8 / U3).

    The route *template* is the label (``/api/v1/product/{product_id}``), never
    the raw path: a path per product would be as many series as products.
    Unmatched paths (404 scans) are grouped under ``unmatched``.
    """
    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        template = getattr(request.scope.get("route"), "path", None)
        if (
            template
            and not template.startswith(settings.API_V1_STR)
            and template != "/metrics"
        ):
            template = f"{settings.API_V1_STR}{template}"
        http_metrics.observe(
            request.method.upper(),
            template or "unmatched",
            status,
            time.perf_counter() - started,
        )


from app.api.routes import metrics as _metrics_routes  # noqa: E402

app.include_router(_metrics_routes.router)
