"""Outbox consumer worker entrypoint with consumer-side idempotency."""

import importlib
import logging
from typing import Any

from arq.worker import Retry
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.alerting import send_alert
from app.core.db import engine

logger = logging.getLogger(__name__)

OUTBOX_CONSUMER_IDEMPOTENCY_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days

# Transient-failure retry policy. A handler that raises is re-enqueued with an
# exponential backoff capped at OUTBOX_HANDLER_RETRY_MAX_DEFER_SECONDS:
# 10 s, 20 s, 40 s, 80 s, 160 s, 300 s, 300 s — about 15 minutes of coverage,
# enough to ride out a ClamAV / Mailgun / supplier-API outage. (The previous
# 5 tries gave up after 2 min 30 and never reached the 300 s cap at all.)
#
# ``WorkerSettings.functions`` registers this entrypoint with max_tries set from
# OUTBOX_HANDLER_MAX_TRIES, so arq and this module cannot drift apart.
#
# Retrying is safe because handlers are at-least-once by design: the consumer
# idempotency key is only written once a handler returns, and every registered
# handler is written to tolerate a replay (status writes are assignments,
# stock confirm/release skip movements that already left PENDING).
OUTBOX_HANDLER_MAX_TRIES = 8
OUTBOX_HANDLER_RETRY_BASE_SECONDS = 10
OUTBOX_HANDLER_RETRY_MAX_DEFER_SECONDS = 300


def build_outbox_consumer_key(event_id: str, handler_path: str) -> str:
    """Build outbox consumer key."""
    return f"outbox:consumer:processed:{event_id}:{handler_path}"


async def execute_outbox_handler(
    ctx: dict[str, Any],
    handler_path: str,
    event_id: str,
    event_type: str,
    payload: dict[str, Any],
    **_kwargs: Any,
) -> None:
    """Resolve and execute a registered outbox handler once for a given delivery."""
    try:
        idempotency_key = build_outbox_consumer_key(event_id, handler_path)
        redis = ctx.get("redis")

        if redis is not None:
            already_processed = await redis.get(idempotency_key)
            if already_processed:
                logger.info(
                    "Skipping already processed outbox delivery for event_id=%s handler=%s",
                    event_id,
                    handler_path,
                )
                return

        mod, func = handler_path.split(":")
        module = importlib.import_module(mod)
        handler = getattr(module, func)

        logger.debug(
            "Executing outbox handler %s for event_id=%s event_type=%s",
            handler_path,
            event_id,
            event_type,
        )

        async with AsyncSession(engine) as session:
            await handler(session, payload)

        if redis is not None:
            await redis.set(
                idempotency_key,
                "1",
                ex=OUTBOX_CONSUMER_IDEMPOTENCY_TTL_SECONDS,
            )

        logger.debug("Successfully executed handler %s", handler_path)

    except Retry:
        raise
    except Exception as e:
        # Retry with exponential backoff: a transient outage (ClamAV, Mailgun,
        # supplier API…) must not permanently lose the AV scan / email / PO.
        job_try = int(ctx.get("job_try") or 1)
        if job_try >= OUTBOX_HANDLER_MAX_TRIES:
            # Stable marker for alerting: past this point nothing replays the
            # delivery on its own — it needs `outbox.health.recover_missing_jobs`
            # or a manual re-enqueue.
            logger.error(
                "OUTBOX_DELIVERY_ABANDONED handler=%s event_id=%s event_type=%s "
                "tries=%s error=%s — no further retry, manual replay required",
                handler_path,
                event_id,
                event_type,
                job_try,
                str(e),
            )
            # Abandon définitif = perte d'effet (scan AV, email, PO…) : alerte
            # webhook pour déclencher le rejeu manuel (runbook --mode retry).
            await send_alert(
                f"handler outbox {handler_path} abandonné après {job_try} "
                f"tentatives (event {event_id}, type {event_type}) : {e}",
                source="arq-worker",
            )
            raise
        defer_seconds = min(
            OUTBOX_HANDLER_RETRY_BASE_SECONDS * 2 ** (job_try - 1),
            OUTBOX_HANDLER_RETRY_MAX_DEFER_SECONDS,
        )
        logger.warning(
            "Failed to execute handler %s for event_id=%s (try %s/%s), "
            "retrying in %ss: %s",
            handler_path,
            event_id,
            job_try,
            OUTBOX_HANDLER_MAX_TRIES,
            defer_seconds,
            str(e),
        )
        raise Retry(defer=defer_seconds) from e
