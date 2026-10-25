"""The one way the shop sends an e-mail.

Every message goes through :func:`send_email` (now, in the caller's flow) or
:func:`queue_email` (by the ARQ worker, for public forms: no provider
latency in the request, no timing difference telling whether an account
exists). Both write an :class:`EmailLog` row, so the admin can see what was
sent and send it again (:func:`resend`).

Before, ten call sites each picked their provider, sent, and logged a
warning on failure — nothing kept track of what had been sent.

The journal is written in its own transaction on the caller's connection
pool: it survives a caller that never commits (an outbox handler that only
sends), and a journal that cannot be written never stops the e-mail.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.logging_config import mask_email
from app.features.notification.models.email_log import (
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_SENT,
    EmailLog,
)
from app.features.notification.providers import get_notification_provider
from app.features.notification.providers.base import (
    NotificationMessage,
    NotificationResult,
    UnknownNotificationProviderError,
)

logger = logging.getLogger(__name__)

SEND_QUEUED_EMAIL_TASK = "send_queued_email_task"


def _provider_code() -> str:
    return settings.PAYMENT_NOTIFICATIONS_EMAIL_PROVIDER


def _new_log(
    *,
    recipient: str,
    subject: str | None,
    text: str,
    html: str | None,
    event_type: str,
    resendable: bool,
) -> EmailLog:
    return EmailLog(
        event_type=event_type[:100],
        recipient=recipient.strip(),
        subject=(subject or "")[:500],
        body_text=text,
        body_html=html,
        resendable=resendable,
        provider_code=_provider_code(),
    )


async def deliver(
    log: EmailLog,
    *,
    attachments: list[tuple[str, bytes, str]] | None = None,
    metadata: dict[str, object] | None = None,
) -> NotificationResult:
    """Send the message of ``log`` and record the outcome on it (no commit)."""
    log.attempts += 1
    try:
        provider = get_notification_provider(log.provider_code or _provider_code())
    except UnknownNotificationProviderError as exc:
        result = NotificationResult(
            provider_code=log.provider_code or "", delivered=False, error=str(exc)
        )
    else:
        result = await provider.send(
            NotificationMessage(
                channel="email",
                recipient=log.recipient,
                subject=log.subject,
                text=log.body_text or "",
                html=log.body_html,
                metadata={"event_type": log.event_type, **(metadata or {})},
                attachments=attachments,
            )
        )
    if result.delivered:
        log.status = STATUS_SENT
        log.sent_at = datetime.now(UTC)
        log.last_error = None
        if not log.resendable:
            # A reset link or a sign-up code: never kept once sent.
            log.body_text = None
            log.body_html = None
    else:
        log.status = STATUS_FAILED
        log.last_error = (result.error or "not delivered")[:500]
        logger.warning(
            "e-mail %s to %s not delivered: %s",
            log.event_type,
            mask_email(log.recipient),
            result.error,
        )
    return result


async def _save(session: AsyncSession, log: EmailLog) -> None:
    """Write ``log`` in a transaction of its own (never raises)."""
    try:
        async with AsyncSession(_bind(session), expire_on_commit=False) as own:
            await own.merge(log)
            await own.commit()
    except Exception:  # noqa: BLE001 — the journal never blocks a message
        logger.warning(
            "e-mail journal unavailable for %s", log.event_type, exc_info=True
        )


def _bind(session: AsyncSession) -> Any:
    return session.bind


async def send_email(
    session: AsyncSession,
    *,
    recipient: str,
    subject: str | None,
    text: str,
    html: str | None,
    event_type: str,
    attachments: list[tuple[str, bytes, str]] | None = None,
    metadata: dict[str, object] | None = None,
    resendable: bool = True,
) -> NotificationResult:
    """Send now and journal it (a message with attachments is resent
    without them). ``session`` only gives the connection: nothing is added
    to it, the caller's transaction is left alone."""
    log = _new_log(
        recipient=recipient,
        subject=subject,
        text=text,
        html=html,
        event_type=event_type,
        resendable=resendable,
    )
    result = await deliver(log, attachments=attachments, metadata=metadata)
    await _save(session, log)
    return result


async def queue_email(
    session: AsyncSession,
    *,
    recipient: str,
    subject: str | None,
    text: str,
    html: str | None,
    event_type: str,
    resendable: bool = True,
) -> uuid.UUID:
    """Journal the message and hand it to the worker.

    If the queue cannot be reached the message is sent here instead: a
    sign-up code that never leaves is worse than a slower request.
    """
    log = _new_log(
        recipient=recipient,
        subject=subject,
        text=text,
        html=html,
        event_type=event_type,
        resendable=resendable,
    )
    await _save(session, log)
    if not await _enqueue(log.id):
        await deliver(log)
        await _save(session, log)
    return log.id


async def _enqueue(log_id: uuid.UUID) -> bool:
    from app.core.arq_worker import get_redis_pool

    try:
        pool = await get_redis_pool()
        await pool.enqueue_job(
            SEND_QUEUED_EMAIL_TASK, log_id=str(log_id), _job_id=f"email-{log_id}"
        )
    except Exception:  # noqa: BLE001 — any queue failure falls back to sending now
        logger.warning("e-mail queue unavailable, sending %s inline", log_id)
        return False
    return True


async def send_queued(session: AsyncSession, log_id: uuid.UUID) -> EmailLog | None:
    """Worker side: send a queued message (idempotent: a sent one is left
    alone). Commits."""
    log = await session.get(EmailLog, log_id)
    if log is None or log.status == STATUS_SENT:
        return log
    await deliver(log)
    session.add(log)
    await session.commit()
    await session.refresh(log)  # read after the commit (worker, admin screen)
    return log


async def resend(session: AsyncSession, log: EmailLog) -> EmailLog:
    """Send a journaled message again, through the worker. Commits.

    The caller refuses a message that is not resendable (its body is gone).
    A new job id each time: the first job of this row may still be known.
    """
    log.status = STATUS_QUEUED
    log.last_error = None
    session.add(log)
    await session.commit()
    from app.core.arq_worker import get_redis_pool

    try:
        pool = await get_redis_pool()
        await pool.enqueue_job(SEND_QUEUED_EMAIL_TASK, log_id=str(log.id))
    except Exception:  # noqa: BLE001
        await deliver(log)
        session.add(log)
        await session.commit()
    return log


__all__ = [
    "SEND_QUEUED_EMAIL_TASK",
    "deliver",
    "queue_email",
    "resend",
    "send_email",
    "send_queued",
]
