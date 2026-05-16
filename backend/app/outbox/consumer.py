"""Outbox consumer worker entrypoint with consumer-side idempotency."""

import importlib
import logging
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import engine

logger = logging.getLogger(__name__)

OUTBOX_CONSUMER_IDEMPOTENCY_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days


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

    except Exception as e:
        logger.error("Failed to execute handler %s: %s", handler_path, str(e))
        raise
