"""Sentry for every process (R8 / U3): API, worker, poller, health checker.

Only the API was initialised; a handler crashing in the worker was invisible.
``SENTRY_DSN`` empty or ``ENVIRONMENT=local`` → nothing is sent.
"""

from __future__ import annotations

import sentry_sdk

from app.core.config import settings


def init_sentry(component: str) -> bool:
    """Initialise the SDK for this process; returns whether it is active."""
    if not settings.SENTRY_DSN or settings.ENVIRONMENT == "local":
        return False
    sentry_sdk.init(
        dsn=str(settings.SENTRY_DSN),
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        # Sans ça staging et production se mélangent dans la même vue.
        environment=settings.ENVIRONMENT,
        release=settings.APP_RELEASE or None,
    )
    sentry_sdk.set_tag("component", component)
    return True


__all__ = ["init_sentry"]
