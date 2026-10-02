"""``GET /metrics`` (R8 / U3): Prometheus exposition of this API process."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Request, Response

from app.api.deps import SessionDep
from app.core.config import settings
from app.core.errors import AppError
from app.core.metrics import render_metrics

router = APIRouter(tags=["utils"])

CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


def _authorize(request: Request) -> None:
    """``METRICS_TOKEN`` as a bearer, else only reachable in ``local``."""
    token = (settings.METRICS_TOKEN or "").strip()
    if token:
        header = request.headers.get("authorization", "")
        presented = header[7:].strip() if header.lower().startswith("bearer ") else ""
        if presented and secrets.compare_digest(presented, token):
            return
        raise AppError(
            code="metrics.unauthorized",
            status_code=401,
            message="Metrics require the METRICS_TOKEN bearer",
        )
    if settings.ENVIRONMENT != "local":
        # Not configured: the endpoint does not exist, rather than leak the
        # route templates and traffic of the shop.
        raise AppError(code="metrics.disabled", status_code=404, message="Not found")


@router.get("/metrics", include_in_schema=False)
async def get_metrics(request: Request, session: SessionDep) -> Response:
    """Latency and errors of this process, ARQ queue depth, outbox age."""
    _authorize(request)
    body = await render_metrics(session)
    return Response(content=body, media_type=CONTENT_TYPE)
