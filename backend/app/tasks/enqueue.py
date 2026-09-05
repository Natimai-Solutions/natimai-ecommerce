"""Enqueue an ARQ job once: a short-lived Redis key absorbs duplicate triggers.

Shared by the supplier syncs and the price refresh. A trigger fired twice
within the window (an admin double-click, two scheduler ticks racing) returns
the already-queued job id instead of a second job.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from typing import Any, cast
from uuid import uuid4

logger = logging.getLogger(__name__)


async def enqueue_with_dedup(
    function: str,
    *,
    dedup_namespace: str,
    job_prefix: str,
    payload_key: list[str] | None,
    job_kwargs: dict[str, Any],
    window_seconds: int = 10,
) -> str:
    """Enqueue ``function`` unless the same payload was queued within the window."""
    from app.core.arq_worker import get_redis_pool

    redis = await get_redis_pool()

    key_material = json.dumps(sorted(payload_key) if payload_key else []).encode()
    dedup_key = f"{dedup_namespace}:{hashlib.md5(key_material).hexdigest()}"  # noqa: S324
    job_id = (
        f"{job_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    )

    was_set = await redis.set(dedup_key, job_id.encode(), ex=window_seconds, nx=True)
    if not was_set:
        existing = await redis.get(dedup_key)
        logger.debug(
            "%s already queued/running: %s",
            function,
            existing.decode() if existing else "unknown",
        )
        return existing.decode() if existing else job_id

    job = await redis.enqueue_job(
        function,
        _job_id=job_id,
        _max_tries=1,  # manual jobs: no automatic retry
        **job_kwargs,
    )
    logger.info("%s triggered with job ID: %s", function, job.job_id)
    return cast(str, job.job_id)
