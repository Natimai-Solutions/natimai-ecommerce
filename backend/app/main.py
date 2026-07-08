from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI, Request, Response
from fastapi.routing import APIRoute
from starlette.middleware.cors import CORSMiddleware

from app.api import api_router
from app.core.config import settings
from app.core.errors import register_error_handlers
from app.outbox.loader import load_handlers


def custom_generate_unique_id(route: APIRoute) -> str:
    """Execute custom generate unique id."""
    return f"{route.tags[0]}-{route.name}"


if settings.SENTRY_DSN and settings.ENVIRONMENT != "local":
    sentry_sdk.init(dsn=str(settings.SENTRY_DSN), enable_tracing=True)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup
    """Execute lifespan."""
    print("Loading outbox handlers...")
    load_handlers()

    # Vérifier que les handlers sont bien enregistrés
    from app.outbox.registry import outbox_registry

    print(f"Handlers enregistrés: {list(outbox_registry.handlers.keys())}")

    yield

    # Shutdown
    print("Shutting down...")


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
    if settings.ENVIRONMENT != "local":
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response

# Set all CORS enabled origins
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            str(origin).strip("/") for origin in settings.BACKEND_CORS_ORIGINS
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router, prefix=settings.API_V1_STR)
