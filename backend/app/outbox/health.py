"""
Health check system for outbox and ARQ jobs consistency.

This module provides functionality to detect and recover from:
- ARQ worker crashes leaving jobs stranded in Redis
- Outbox events marked as DONE but ARQ jobs failed silently
- Redis/ARQ connectivity issues
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.arq_pool import get_arq_pool
from app.core.db import engine
from app.outbox.models import OutboxEvent

logger = logging.getLogger(__name__)


class OutboxHealthChecker:
    """
    Health checker for outbox/ARQ consistency.

    Detects and recovers from:
    - Events marked DONE but ARQ jobs still queued/failed
    - ARQ jobs lost due to worker crashes
    - Stale jobs in Redis without corresponding outbox events
    """

    def __init__(self, stale_threshold_minutes: int = 10) -> None:
        """
        Initialize health checker.

        Args:
            stale_threshold_minutes: Consider jobs stale after this many minutes
        """
        self.stale_threshold = timedelta(minutes=stale_threshold_minutes)

    async def check_orphaned_jobs(self) -> dict[str, Any]:
        """
        Check for ARQ jobs without corresponding outbox events or vice versa.

        Returns:
            Dict with health check results and stats
        """
        try:
            arq_pool = await get_arq_pool()  # type: ignore[no-untyped-call]

            # Get all pending/running ARQ jobs with outbox prefix
            redis_client = arq_pool._redis

            # ARQ uses specific keys for jobs - let's scan for outbox jobs
            outbox_jobs = []
            async for key in redis_client.scan_iter(match="arq:job:outbox:*"):
                job_data = await redis_client.hgetall(key)
                if job_data:
                    outbox_jobs.append(
                        {
                            "key": key.decode(),
                            "job_id": job_data.get(b"job_id", b"").decode(),
                            "status": job_data.get(b"status", b"").decode(),
                            "enqueue_time": job_data.get(b"enqueue_time", b"").decode(),
                        }
                    )

            # Check against outbox events
            async with AsyncSession(engine) as session:
                stmt = (
                    select(OutboxEvent)
                    .where(col(OutboxEvent.status).in_(["RUNNING", "DONE"]))
                    .where(
                        OutboxEvent.updated_at
                        > datetime.now(UTC) - self.stale_threshold
                    )
                )
                result = await session.exec(stmt)
                recent_events = result.all()

            # Analysis
            orphaned_jobs = []
            missing_jobs = []

            # Find Redis jobs without outbox events
            event_ids = {str(event.id) for event in recent_events}
            for job in outbox_jobs:
                job_id_parts = job["job_id"].split(":")
                if len(job_id_parts) >= 2:
                    event_id = job_id_parts[
                        1
                    ]  # Extract UUID from "outbox:uuid:handler"
                    if event_id not in event_ids:
                        orphaned_jobs.append(job)

            # Find outbox events without Redis jobs
            redis_event_ids = set()
            for job in outbox_jobs:
                job_id_parts = job["job_id"].split(":")
                if len(job_id_parts) >= 2:
                    redis_event_ids.add(job_id_parts[1])

            for event in recent_events:
                if str(event.id) not in redis_event_ids and event.status == "RUNNING":
                    missing_jobs.append(
                        {
                            "event_id": str(event.id),
                            "type": event.type,
                            "status": event.status,
                            "updated_at": event.updated_at.isoformat(),
                        }
                    )

            return {
                "status": "healthy"
                if not orphaned_jobs and not missing_jobs
                else "degraded",
                "timestamp": datetime.now(UTC).isoformat(),
                "stats": {
                    "redis_jobs": len(outbox_jobs),
                    "recent_events": len(recent_events),
                    "orphaned_jobs": len(orphaned_jobs),
                    "missing_jobs": len(missing_jobs),
                },
                "issues": {
                    "orphaned_jobs": orphaned_jobs,
                    "missing_jobs": missing_jobs,
                },
            }

        except Exception as e:
            logger.error("Health check failed: %s", str(e))
            return {
                "status": "error",
                "timestamp": datetime.now(UTC).isoformat(),
                "error": str(e),
            }

    async def recover_missing_jobs(self) -> dict[str, Any]:
        """
        Recover from missing ARQ jobs by resetting outbox events to PENDING.

        This allows the poller to re-enqueue them.
        """
        recovered = []

        try:
            health_status = await self.check_orphaned_jobs()
            missing_jobs = health_status.get("issues", {}).get("missing_jobs", [])

            if not missing_jobs:
                return {"recovered": 0, "events": []}

            async with AsyncSession(engine) as session:
                for missing in missing_jobs:
                    stmt = select(OutboxEvent).where(
                        OutboxEvent.id == missing["event_id"]
                    )
                    result = await session.exec(stmt)
                    event = result.first()

                    if event and event.status == "RUNNING":
                        # Reset to PENDING for re-processing
                        event.status = "PENDING"
                        event.attempts += 1
                        event.next_run_at = datetime.now(UTC)
                        event.last_error = "Recovered from missing ARQ job"
                        session.add(event)

                        recovered.append(
                            {
                                "event_id": str(event.id),
                                "type": event.type,
                                "attempt": event.attempts,
                            }
                        )

                await session.commit()

            logger.debug("Recovered %d missing jobs", len(recovered))
            return {"recovered": len(recovered), "events": recovered}

        except Exception as e:
            logger.error("Recovery failed: %s", str(e))
            return {"recovered": 0, "error": str(e)}


# Global instance
health_checker = OutboxHealthChecker()


async def run_health_check() -> dict[str, Any]:
    """
    Run a complete health check and recovery.

    Usage:
        python -c "import asyncio; from app.outbox.health import run_health_check; asyncio.run(run_health_check())"
    """
    logger.debug("Starting outbox health check...")

    # Check for issues
    health_status = await health_checker.check_orphaned_jobs()

    logger.info(
        "Outbox health: %s", health_status["status"], extra=dict(health_status["stats"])
    )

    # Recover if needed
    if health_status["stats"]["missing_jobs"] > 0:
        recovery_result = await health_checker.recover_missing_jobs()
        logger.info("Recovered %s outbox events", recovery_result["recovered"])

    return health_status


if __name__ == "__main__":
    asyncio.run(run_health_check())
