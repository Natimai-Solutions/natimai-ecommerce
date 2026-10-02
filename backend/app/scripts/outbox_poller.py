#!/usr/bin/env python3
"""
Standalone Outbox Event Poller Script.

This script provides a standalone process for polling and processing outbox events.
It can be run as a separate service or as a cron job to ensure reliable event processing.
The script supports multiple operation modes and provides comprehensive logging.

Usage:
    python app/scripts/outbox_poller.py [--mode MODE] [--interval SECONDS] [--max-events COUNT]

Modes:
    - continuous: Run continuously with polling interval (default)
    - once: Process all pending events once and exit
    - single: Process a single event and exit
    - retry: Retry failed events and exit
    - cleanup: Clean up old events and exit

Examples:
    # Run continuously with 5-second polling
    python app/scripts/outbox_poller.py --mode continuous --interval 5

    # Process all pending events once
    python app/scripts/outbox_poller.py --mode once

    # Retry failed events
    python app/scripts/outbox_poller.py --mode retry

    # Clean up events older than 7 days
    python app/scripts/outbox_poller.py --mode cleanup --days 7
"""

import argparse
import asyncio
import logging
import logging.handlers
import os
import signal
import sys
import time
from pathlib import Path

# Add the app directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import engine
from app.outbox.loader import load_handlers
from app.outbox.poller import OutboxPoller, poll_outbox_once

# Le fichier de log double la sortie standard : stdout est récupéré et tourné
# par Docker (anchor x-app-logging), le fichier ne l'est par personne. Sans
# bornes il grossit tant que le service tourne — c'est-à-dire indéfiniment —
# et remplit la couche inscriptible du conteneur. 5 Mo × 3 archives couvrent
# largement la fenêtre de diagnostic d'un incident outbox.
_LOG_FILE = os.environ.get("OUTBOX_POLLER_LOG_FILE", "outbox_poller.log")
_LOG_MAX_BYTES = 5 * 1024 * 1024
_LOG_BACKUP_COUNT = 3


def _log_handlers() -> list[logging.Handler]:
    """stdout, plus the rotating file when the working directory allows it.

    The hardened image runs as a non-root user with a read-only ``/app``: the
    file handler then raises ``PermissionError`` at start-up and, without this
    guard, the poller dies before polling anything — the payments approved in
    the back-office never reached the worker (CI E2E, 02/10/2026). stdout is
    what Docker collects anyway; the file is a convenience, never a requirement.
    """
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    try:
        handlers.append(
            logging.handlers.RotatingFileHandler(
                _LOG_FILE,
                maxBytes=_LOG_MAX_BYTES,
                backupCount=_LOG_BACKUP_COUNT,
                encoding="utf-8",
            )
        )
    except OSError as exc:
        print(
            f"outbox poller: log file {_LOG_FILE!r} not writable ({exc}); "
            "logging to stdout only",
            file=sys.stderr,
        )
    return handlers


# `force=True` n'est pas décoratif : les imports ci-dessus finissent par
# atteindre app.features.base.crud, qui appelle logging.basicConfig() au chargement
# du module. Le root logger a donc déjà un handler quand on arrive ici, et sans
# `force` cet appel est un no-op silencieux — ni le niveau, ni le format, ni le
# fichier ne s'appliquaient, le fichier étant créé vide puis jamais écrit.
# Ce processus est un service autonome : il a le droit de configurer son propre
# logging (il n'initialise pas Sentry, aucun handler tiers n'est écrasé).
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=_log_handlers(),
    force=True,
)
logger = logging.getLogger(__name__)


class OutboxPollerService:
    """
    Standalone outbox poller service.

    This class provides a standalone service for processing outbox events
    with various operation modes and configuration options.
    """

    def __init__(self) -> None:
        """Initialize the outbox poller service instance."""
        self.running = False
        self.poller = OutboxPoller()

    def setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""

        def signal_handler(signum: int, _frame: object) -> None:
            """Execute signal handler."""
            logger.debug("Received signal %d, shutting down gracefully...", signum)
            self.running = False

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    async def run_continuous(
        self, interval: int = 10, max_events: int | None = None
    ) -> None:
        """
        Run the poller continuously with the specified interval.

        Args:
            interval (int): Polling interval in seconds
            max_events (int): Maximum events to process per batch
        """
        logger.debug(
            "Starting continuous outbox poller (interval: %ds, max_events: %s)",
            interval,
            max_events,
        )

        self.setup_signal_handlers()
        self.running = True

        while self.running:
            try:
                start_time = time.time()

                async with AsyncSession(engine) as session:
                    if max_events:
                        processed = await self.poller.process_pending_events(
                            session, max_events
                        )
                    else:
                        # Process one event at a time for better control
                        processed = 1 if await poll_outbox_once(session) else 0

                if processed > 0:
                    logger.debug("Processed %d events", processed)
                    # Drained an event — loop again immediately instead of waiting
                    # `interval`. Otherwise a backlog (e.g. many skipped
                    # update.product events) clears at only 1/interval and starves
                    # handled events like payment.captured.
                    continue

                # Idle: nothing was due — wait for the polling interval.
                elapsed = time.time() - start_time
                sleep_time = max(0, interval - elapsed)
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

            except Exception as e:
                logger.error("Error in continuous polling: %s", str(e), exc_info=True)
                await asyncio.sleep(
                    interval
                )  # Sleep on error to prevent tight error loop

        logger.debug("Outbox poller service stopped")

    async def run_once(self, max_events: int | None = None) -> int:
        """
        Process all pending events once and exit.

        Args:
            max_events (int): Maximum events to process
        """
        logger.debug("Running outbox poller once (max_events: %s)", max_events)

        try:
            async with AsyncSession(engine) as session:
                processed = await self.poller.process_pending_events(
                    session, max_events
                )
                logger.debug(
                    "One-time processing completed: %d events processed", processed
                )
                return processed
        except Exception as e:
            logger.error("Error in one-time processing: %s", str(e), exc_info=True)
            return 0

    async def run_single(self, event_id: str | None = None) -> int:
        """
        Process a single event and exit.

        Args:
            event_id (str): Specific event ID to process, or None for any pending event
        """
        logger.debug("Processing single event (ID: %s)", event_id or "any")

        try:
            async with AsyncSession(engine) as session:
                if event_id:
                    success = await self.poller.process_single_event(session, event_id)
                    if success:
                        logger.debug("Successfully processed event: %s", event_id)
                        return 1
                    else:
                        logger.warning("Failed to process event: %s", event_id)
                        return 0
                else:
                    success = await poll_outbox_once(session)
                    if success:
                        logger.debug("Successfully processed one pending event")
                        return 1
                    else:
                        logger.debug("No pending events to process")
                        return 0
        except Exception as e:
            logger.error("Error processing single event: %s", str(e), exc_info=True)
            return 0

    async def run_retry(self, max_attempts: int = 5) -> int:
        """
        Retry failed events and exit.

        Args:
            max_attempts (int): Maximum attempts before giving up on an event
        """
        logger.debug("Retrying failed events (max_attempts: %d)", max_attempts)

        try:
            async with AsyncSession(engine) as session:
                retried = await self.poller.retry_failed_events(session, max_attempts)
                logger.debug(
                    "Retry operation completed: %d events reset for retry", retried
                )
                return retried
        except Exception as e:
            logger.error("Error retrying failed events: %s", str(e), exc_info=True)
            return 0

    async def run_cleanup(self, days_old: int = 30) -> int:
        """
        Clean up old events and exit.

        Args:
            days_old (int): Age in days for events to be cleaned up
        """
        logger.debug("Cleaning up events older than %d days", days_old)

        try:
            async with AsyncSession(engine) as session:
                cleaned = await self.poller.cleanup_old_events(session, days_old)
                logger.debug("Cleanup operation completed: %d events removed", cleaned)
                return cleaned
        except Exception as e:
            logger.error("Error cleaning up old events: %s", str(e), exc_info=True)
            return 0


async def main() -> int:
    """Main entry point for the outbox poller script."""
    parser = argparse.ArgumentParser(
        description="Standalone Outbox Event Poller",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--mode",
        choices=["continuous", "once", "single", "retry", "cleanup"],
        default="continuous",
        help="Operation mode (default: continuous)",
    )

    parser.add_argument(
        "--interval",
        type=int,
        default=10,
        help="Polling interval in seconds for continuous mode (default: 10)",
    )

    parser.add_argument(
        "--max-events", type=int, help="Maximum number of events to process per batch"
    )

    parser.add_argument(
        "--event-id", type=str, help="Specific event ID to process (single mode only)"
    )

    parser.add_argument(
        "--max-attempts",
        type=int,
        default=5,
        help="Maximum attempts for retry mode (default: 5)",
    )

    parser.add_argument(
        "--days", type=int, default=30, help="Days old for cleanup mode (default: 30)"
    )

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)",
    )

    args = parser.parse_args()

    # Configure logging level
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    logger.debug("Starting Outbox Poller Service")
    logger.debug("Mode: %s", args.mode)

    try:
        # Load event handlers
        logger.debug("Loading event handlers...")
        load_handlers()
        logger.debug("Event handlers loaded successfully")

        # Initialize and run the service
        service = OutboxPollerService()
        result = 0

        if args.mode == "continuous":
            await service.run_continuous(args.interval, args.max_events)
        elif args.mode == "once":
            result = await service.run_once(args.max_events)
        elif args.mode == "single":
            result = await service.run_single(args.event_id)
        elif args.mode == "retry":
            result = await service.run_retry(args.max_attempts)
        elif args.mode == "cleanup":
            result = await service.run_cleanup(args.days)

        logger.debug("Outbox poller service completed successfully")
        return result

    except KeyboardInterrupt:
        logger.debug("Service interrupted by user")
        return 0
    except Exception as e:
        logger.error("Fatal error in outbox poller service: %s", str(e), exc_info=True)
        return 1


if __name__ == "__main__":
    try:
        result = asyncio.run(main())
        sys.exit(0 if result >= 0 else 1)
    except Exception as e:
        logger.error("Failed to start outbox poller service: %s", str(e))
        sys.exit(1)
