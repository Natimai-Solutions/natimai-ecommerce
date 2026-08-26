"""Outbox health-check scheduler service.

This long-running service continuously verifies consistency between outbox
events and ARQ jobs in production.

Usage:
    python -m app.outbox.health_scheduler

Environment variables:
    HEALTH_CHECK_INTERVAL: Interval in seconds (default: 300, i.e. 5 minutes)
    STALE_THRESHOLD_MINUTES: Threshold for stale jobs (default: 10 minutes)
    RECOVERY_ENABLED: Enable automatic recovery (default: true)
    LOG_LEVEL: Logging level (default: INFO)
"""

import asyncio
import logging
import os
import signal
from datetime import datetime, timezone
from typing import Any, TypedDict

from app.core.alerting import send_alert
from app.outbox.health import health_checker

# Configuration depuis les variables d'environnement
HEALTH_CHECK_INTERVAL = int(os.getenv("HEALTH_CHECK_INTERVAL", "300"))  # 5 minutes
RECOVERY_ENABLED = os.getenv("RECOVERY_ENABLED", "true").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Configuration du logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


class SchedulerStats(TypedDict):
    """Typed metrics snapshot maintained by the scheduler."""

    total_checks: int
    total_recoveries: int
    last_check: str | None
    last_recovery: str | None
    # Dernier statut ALERTÉ (pas observé) — l'alerte webhook ne part que sur
    # changement d'état, pas à chaque cycle de 5 min (anti-spam).
    last_alerted_status: str


class HealthCheckScheduler:
    """Run periodic outbox health checks and optional recovery."""

    def __init__(self) -> None:
        """Initialize the health check scheduler instance."""
        self.running = False
        self.task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the scheduler loop and wait until shutdown."""
        logger.debug("Starting Outbox Health Check Scheduler")
        logger.debug("Check interval: %d seconds", HEALTH_CHECK_INTERVAL)
        logger.debug("Recovery enabled: %s", RECOVERY_ENABLED)

        self.running = True
        self.task = asyncio.create_task(self._run_scheduler())

        # Setup signal handlers pour un arrêt propre
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        await self.task

    def _signal_handler(self, signum: int, _frame: Any) -> None:
        """Handle process signals and stop the scheduler gracefully."""
        logger.debug("Received signal %d, shutting down gracefully", signum)
        self.running = False
        if self.task:
            self.task.cancel()

    async def _run_scheduler(self) -> None:
        """Run the periodic health-check loop."""
        stats: SchedulerStats = {
            "total_checks": 0,
            "total_recoveries": 0,
            "last_check": None,
            "last_recovery": None,
            "last_alerted_status": "healthy",
        }

        while self.running:
            try:
                await self._run_health_check(stats)

                # Log des statistiques périodiques
                if stats["total_checks"] % 12 == 0:  # Toutes les heures si check = 5min
                    logger.debug("Health Check Stats: %s", stats)

                # Attendre avant le prochain check
                await asyncio.sleep(HEALTH_CHECK_INTERVAL)

            except asyncio.CancelledError:
                logger.debug("Scheduler cancelled")
                break
            except Exception as e:
                logger.error("Unexpected error in scheduler: %s", str(e), exc_info=True)
                await asyncio.sleep(30)  # Attendre avant de retry

    async def _run_health_check(self, stats: SchedulerStats) -> None:
        """Execute one health-check cycle and trigger recovery when needed."""
        check_start = datetime.now(timezone.utc)

        try:
            # 1. Vérification de santé
            health_status = await health_checker.check_orphaned_jobs()
            stats["total_checks"] += 1
            stats["last_check"] = check_start.isoformat()

            # Log des résultats
            status = health_status.get("status", "unknown")
            stats_data = health_status.get("stats", {})

            logger.debug(
                "Health Check - Status: %s, Redis Jobs: %d, Recent Events: %d, Issues: %d+%d",
                status,
                stats_data.get("redis_jobs", 0),
                stats_data.get("recent_events", 0),
                stats_data.get("orphaned_jobs", 0),
                stats_data.get("missing_jobs", 0),
            )

            # 2. Récupération automatique si activée
            if RECOVERY_ENABLED and status == "degraded":
                missing_jobs = stats_data.get("missing_jobs", 0)
                if missing_jobs > 0:
                    logger.warning(
                        "Found %d missing jobs, starting recovery", missing_jobs
                    )

                    recovery_result = await health_checker.recover_missing_jobs()
                    recovered = recovery_result.get("recovered", 0)

                    if recovered > 0:
                        stats["total_recoveries"] += recovered
                        stats["last_recovery"] = datetime.now(timezone.utc).isoformat()
                        logger.debug("Successfully recovered %d jobs", recovered)
                    else:
                        logger.warning("Recovery attempted but no jobs recovered")

            # 3. Alerting pour les cas critiques — webhook sur CHANGEMENT
            # d'état uniquement (sinon une panne = une alerte toutes les 5 min).
            if status == "error":
                logger.error(
                    "Health check failed: %s",
                    health_status.get("error", "Unknown error"),
                )
            elif stats_data.get("orphaned_jobs", 0) > 10:
                logger.warning(
                    "High number of orphaned jobs detected: %d",
                    stats_data["orphaned_jobs"],
                )

            if status != stats["last_alerted_status"]:
                if status == "error":
                    await send_alert(
                        "health check en erreur : "
                        f"{health_status.get('error', 'Unknown error')}",
                        source="outbox-health-checker",
                    )
                elif status == "degraded":
                    await send_alert(
                        f"outbox dégradé : {stats_data.get('orphaned_jobs', 0)} "
                        f"job(s) orphelin(s), {stats_data.get('missing_jobs', 0)} "
                        "job(s) manquant(s) (recovery "
                        f"{'active' if RECOVERY_ENABLED else 'DÉSACTIVÉE'})",
                        source="outbox-health-checker",
                    )
                elif stats["last_alerted_status"] in {"degraded", "error"}:
                    await send_alert(
                        "outbox rétabli (healthy)",
                        source="outbox-health-checker",
                    )
                stats["last_alerted_status"] = status

        except Exception as e:
            logger.error("Health check execution failed: %s", str(e), exc_info=True)


async def main() -> None:
    """Start the outbox health-check service entrypoint."""
    logger.debug("Outbox Health Check Service starting...")

    scheduler = HealthCheckScheduler()

    try:
        await scheduler.start()
    except KeyboardInterrupt:
        logger.debug("Service stopped by user")
    except Exception as e:
        logger.error("Service crashed: %s", str(e), exc_info=True)
        raise
    finally:
        logger.debug("Outbox Health Check Service stopped")


if __name__ == "__main__":
    asyncio.run(main())
