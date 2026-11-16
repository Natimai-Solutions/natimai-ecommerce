"""ARQ task: send a journaled e-mail (``mailer.queue_email`` / ``resend``)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from arq import Retry
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import engine
from app.features.notification.mailer import send_queued
from app.features.notification.models.email_log import STATUS_FAILED

logger = logging.getLogger(__name__)

#: A provider outage of a few minutes does not lose the message.
EMAIL_MAX_TRIES = 5


async def send_queued_email_task(ctx: dict[str, Any], *, log_id: str) -> str:
    """Send one queued message; retried with backoff while it fails."""
    async with AsyncSession(engine) as session:
        log = await send_queued(session, uuid.UUID(log_id))
    if log is None:
        logger.warning("Queued e-mail %s not found", log_id)
        return "missing"
    if log.status == STATUS_FAILED and int(ctx.get("job_try", 1)) < EMAIL_MAX_TRIES:
        raise Retry(defer=30 * int(ctx.get("job_try", 1)))
    if log.status == STATUS_FAILED:
        await _alert_failed_email(log.event_type, log.last_error)
    return log.status


#: At most one alert per window: an expired provider key fails every mail.
_ALERT_WINDOW_SECONDS = 3600


async def _alert_failed_email(event_type: str, error: str | None) -> None:
    """A message given up after its retries: the shop is told (once an hour).

    An expired Mailgun key stopped every e-mail — order confirmations,
    invoices, password resets — with nothing but a line in ``email_log``
    (functional audit, November 2026)."""
    try:
        from app.core.rate_limit import shared_redis

        first = await shared_redis().set(
            "alert:email_failed", "1", nx=True, ex=_ALERT_WINDOW_SECONDS
        )
    except Exception:  # noqa: BLE001 - no Redis: alert anyway
        first = True
    if not first:
        return
    from app.core.alerting import send_alert

    await send_alert(
        f"E-mail abandonné après {EMAIL_MAX_TRIES} tentatives ({event_type}) : "
        f"{(error or '')[:200]}. Vérifiez le fournisseur d'e-mails ; d'autres "
        "envois échouent peut-être (journal des e-mails).",
        source="email",
    )
