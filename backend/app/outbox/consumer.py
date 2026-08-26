"""Outbox consumer worker entrypoint with consumer-side idempotency."""

import importlib
import logging
from typing import Any

from arq.worker import Retry
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import engine

logger = logging.getLogger(__name__)

OUTBOX_CONSUMER_IDEMPOTENCY_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days

# Transient-failure retry policy: a handler that raises is re-enqueued with an
# exponential backoff (10 s, 20 s, 40 s, 80 s) before being abandoned. Handlers
# are at-least-once by design (idempotency key set only on success), so a retry
# after a partial failure is safe. Keep in sync with WorkerSettings.max_tries.
OUTBOX_HANDLER_MAX_TRIES = 5
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
            logger.error(
                "Failed to execute handler %s for event_id=%s after %s tries "
                "— giving up: %s",
                handler_path,
                event_id,
                job_try,
                str(e),
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
