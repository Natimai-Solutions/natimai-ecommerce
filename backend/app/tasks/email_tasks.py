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
    return log.status
