"""
Outbox Event Poller for processing pending events.

This module provides the outbox poller functionality that processes pending events
by dispatching them to registered handlers via ARQ (async job queue). The poller
ensures reliable event processing with retry logic and exponential backoff.
"""

import importlib
import logging
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.arq_pool import get_arq_pool
from app.outbox.models import OutboxEvent
from app.outbox.registry import outbox_registry

logger = logging.getLogger(__name__)

# Exponential backoff intervals in seconds
BACKOFF = [10, 30, 60, 300, 900]  # 10s, 30s, 1m, 5m, 15m
MAX_ATTEMPTS = 5  # After 5 attempts, mark as FAILED


async def commit_and_refresh(session: AsyncSession, event: OutboxEvent) -> OutboxEvent:
    """
    Commit the session and refresh the event object to avoid detached instance errors.

    After a session.commit(), SQLAlchemy objects become detached from the session.
    This utility function commits and then refreshes the object to reattach it,
    preventing MissingGreenlet and other SQLAlchemy errors when accessing attributes.

    Args:
        session (AsyncSession): Database session
        event (OutboxEvent): Event object to refresh after commit

    Returns:
        OutboxEvent: The refreshed event object
    """
    await session.commit()
    await session.refresh(event)
    return event


def resolve(path: str) -> Callable[..., Any]:
    """
    Resolve a function from a module path string.

    Args:
        path (str): Module path in format "module.path:function_name"

    Returns:
        Callable: The resolved function

    Raises:
        ImportError: If module cannot be imported
        AttributeError: If function is not found in module
    """
    try:
        mod, func = path.split(":")
        module = importlib.import_module(mod)
        return cast(Callable[..., Any], getattr(module, func))
    except (ValueError, ImportError, AttributeError) as e:
        logger.error("Failed to resolve function path %s: %s", path, str(e))
        raise


async def maybe_await(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """
    Call a function and await it if it's async.

    Args:
        fn: Function to call (sync or async)
        *args: Positional arguments
        **kwargs: Keyword arguments

    Returns:
        Any: Function result
    """
    result = fn(*args, **kwargs)
    if hasattr(result, "__await__"):
        return await result
    return result


async def enqueue_jobs_for_event(event: OutboxEvent) -> None:
    """
    Use the registry to send handlers to ARQ for processing.

    This function retrieves all registered handlers for the event type
    and enqueues them as ARQ jobs for asynchronous processing.

    Args:
        event (OutboxEvent): The outbox event to process

    Raises:
        Exception: If no handlers found or ARQ enqueue fails
    """
    try:
        logger.debug("Processing event ID %s of type: %s", event.id, event.type)

        arq_pool = await get_arq_pool()  # type: ignore[no-untyped-call]

        # Get handlers from registry
        handlers = outbox_registry.get_handlers(event.type)

        if not handlers:
            error_msg = f"No handlers found for event type: {event.type}"
            logger.error(error_msg)
            raise Exception(error_msg)

        logger.debug(
            "Found %d handlers for event type %s (ID: %s)",
            len(handlers),
            event.type,
            event.id,
        )

        # Enqueue each handler
        jobs_enqueued = 0
        for handler in handlers:
            try:
                job_id = f"outbox:{event.id}:{handler.__name__}"
                handler_path = f"{handler.__module__}:{handler.__name__}"

                logger.debug("Enqueuing job %s for handler: %s", job_id, handler_path)

                # Enqueue the handler with the payload
                await arq_pool.enqueue_job(
                    handler_path, **event.payload, _job_id=job_id
                )
                jobs_enqueued += 1

            except Exception as e:
                logger.error(
                    "Failed to enqueue handler %s for event %s: %s",
                    handler.__name__,
                    event.id,
                    str(e),
                )
                raise

        logger.debug(
            "Successfully enqueued %d jobs for event %s", jobs_enqueued, event.id
        )

    except Exception as e:
        logger.error("Failed to enqueue jobs for event %s: %s", event.id, str(e))
        raise


async def poll_outbox_once(session: AsyncSession) -> bool:
    """
    Process one pending event that is due. Returns True if something was processed.

    This function selects the oldest pending event that is due for processing,
    marks it as running, processes it via ARQ handlers, and updates its status.

    Args:
        session (AsyncSession): Database session

    Returns:
        bool: True if an event was processed, False if no events were due
    """
    try:
        logger.debug("Polling for pending outbox events")

        # Select 1 due event
        result = await session.exec(
            select(OutboxEvent)
            .where(OutboxEvent.status == "PENDING")
            .where(OutboxEvent.next_run_at <= datetime.now(timezone.utc))
            .order_by(col(OutboxEvent.created_at))
            .limit(1)
        )
        event = result.first()

        if not event:
            logger.debug("No pending events found")
            return False

        logger.debug("Processing outbox event ID %s of type: %s", event.id, event.type)

        # Mark as RUNNING
        event.status = "RUNNING"
        event.touch()
        session.add(event)
        event = await commit_and_refresh(session, event)

        try:
            await enqueue_jobs_for_event(event)

            # If everything was enqueued successfully, mark as DONE
            event.status = "DONE"
            event.attempts += 1
            event.touch()
            session.add(event)
            event = await commit_and_refresh(session, event)

            logger.debug("Successfully processed event ID %s", event.id)

        except Exception as e:
            # Retry with exponential backoff or mark as FAILED
            logger.warning("Event processing failed, scheduling retry: %s", str(e))

            event.status = "PENDING"
            event.attempts += 1
            idx = min(event.attempts - 1, len(BACKOFF) - 1)
            delay_seconds = BACKOFF[idx]
            event.next_run_at = datetime.now(timezone.utc) + timedelta(
                seconds=delay_seconds
            )
            event.last_error = str(e)[:1000]
            event.touch()
            session.add(event)
            event = await commit_and_refresh(session, event)

            logger.debug(
                "Scheduled event %s for retry in %d seconds (attempt %d)",
                event.id,
                delay_seconds,
                event.attempts,
            )

        return True

    except Exception as e:
        logger.error("Critical error in poll_outbox_once: %s", str(e), exc_info=True)
        return False


class OutboxPoller:
    """
    Outbox event poller for processing pending events.

    This class provides methods for processing outbox events by dispatching
    them to registered handlers via ARQ. It includes functionality for
    processing all pending events, individual events, and retrying failed events.
    """

    def __init__(self) -> None:
        logger.debug("Initialized OutboxPoller")

    async def process_pending_events(
        self, session: AsyncSession, limit: int | None = None
    ) -> int:
        """
        Process all pending events by sending them to ARQ.

        This method retrieves all pending events that are due for processing
        and dispatches them to their registered handlers via ARQ.

        Args:
            session (AsyncSession): Database session
            limit (Optional[int]): Maximum number of events to process

        Returns:
            int: Number of events processed
        """
        try:
            logger.debug(
                "Starting batch processing of pending events (limit: %s)", limit
            )

            arq_pool = await get_arq_pool()  # type: ignore[no-untyped-call]

            # Get all pending events that are due
            query = (
                select(OutboxEvent)
                .where(OutboxEvent.status == "PENDING")
                .where(OutboxEvent.next_run_at <= datetime.now(timezone.utc))
                .order_by(col(OutboxEvent.created_at))
            )

            if limit:
                query = query.limit(limit)

            result = await session.exec(query)
            pending_events = result.all()

            if not pending_events:
                logger.debug("No pending events found for processing")
                return 0

            logger.debug("Found %d pending events to process", len(pending_events))
            processed_count = 0
            failed_count = 0

            for event in pending_events:
                try:
                    logger.debug(
                        "Processing event ID %s of type: %s", event.id, event.type
                    )

                    # Mark as RUNNING
                    event.status = "RUNNING"
                    event.touch()
                    session.add(event)
                    event = await commit_and_refresh(session, event)

                    # Get handlers for this event
                    handlers = outbox_registry.get_handlers(event.type)

                    if not handlers:
                        error_msg = f"No handlers found for event type: {event.type}"
                        logger.error(error_msg)
                        raise Exception(error_msg)

                    # Send each handler to ARQ
                    for handler in handlers:
                        job_id = f"outbox:{event.id}:{handler.__name__}"
                        handler_path = f"{handler.__module__}:{handler.__name__}"

                        await arq_pool.enqueue_job(
                            handler_path, **event.payload, _job_id=job_id
                        )

                    # Mark as DONE if everything went well
                    event.status = "DONE"
                    event.attempts += 1
                    event.touch()
                    session.add(event)
                    event = await commit_and_refresh(session, event)

                    processed_count += 1
                    logger.debug("Successfully processed event ID %s", event.id)

                except Exception as e:
                    # Handle failure with backoff
                    logger.warning(
                        "Failed to process event ID %s: %s", event.id, str(e)
                    )

                    event.status = "PENDING"
                    event.attempts += 1
                    idx = min(event.attempts - 1, len(BACKOFF) - 1)
                    delay_seconds = BACKOFF[idx]
                    event.next_run_at = datetime.now(timezone.utc) + timedelta(
                        seconds=delay_seconds
                    )
                    event.last_error = str(e)[:1000]
                    event.touch()
                    session.add(event)
                    event = await commit_and_refresh(session, event)

                    failed_count += 1

            logger.debug(
                "Batch processing completed: %d processed, %d failed",
                processed_count,
                failed_count,
            )
            return processed_count

        except Exception as e:
            logger.error(
                "Critical error in process_pending_events: %s", str(e), exc_info=True
            )
            return 0

    async def process_single_event(self, session: AsyncSession, event_id: str) -> bool:
        """
        Process a specific event by its ID.

        Args:
            session (AsyncSession): Database session
            event_id (str): ID of the event to process

        Returns:
            bool: True if event was processed successfully, False otherwise
        """
        try:
            logger.debug("Processing single event ID: %s", event_id)

            result = await session.exec(
                select(OutboxEvent).where(OutboxEvent.id == event_id)
            )
            event = result.first()

            if not event:
                logger.warning("Event not found: %s", event_id)
                return False

            if event.status != "PENDING":
                logger.warning(
                    "Event %s is not in PENDING status (current: %s)",
                    event_id,
                    event.status,
                )
                return False

            try:
                event.status = "RUNNING"
                event.touch()
                session.add(event)
                event = await commit_and_refresh(session, event)

                await enqueue_jobs_for_event(event)

                event.status = "DONE"
                event.attempts += 1
                event.touch()
                session.add(event)
                event = await commit_and_refresh(session, event)

                logger.debug("Successfully processed single event: %s", event_id)
                return True

            except Exception as e:
                logger.warning(
                    "Failed to process single event %s: %s", event_id, str(e)
                )

                event.status = "PENDING"
                event.attempts += 1
                idx = min(event.attempts - 1, len(BACKOFF) - 1)
                delay_seconds = BACKOFF[idx]
                event.next_run_at = datetime.now(timezone.utc) + timedelta(
                    seconds=delay_seconds
                )
                event.last_error = str(e)[:1000]
                event.touch()
                session.add(event)
                event = await commit_and_refresh(session, event)

                logger.debug(
                    "Scheduled event %s for retry in %d seconds",
                    event_id,
                    delay_seconds,
                )
                return False

        except Exception as e:
            logger.error(
                "Critical error processing single event %s: %s",
                event_id,
                str(e),
                exc_info=True,
            )
            return False

    async def retry_failed_events(
        self, session: AsyncSession, max_attempts: int = 5
    ) -> int:
        """
        Reset FAILED events back to PENDING if they haven't exceeded max attempts.

        This method allows failed events to be retried by resetting their status
        to PENDING so they can be picked up by the poller again.

        Args:
            session (AsyncSession): Database session
            max_attempts (int): Maximum number of attempts before giving up. Defaults to 5.

        Returns:
            int: Number of events reset for retry
        """
        try:
            logger.debug("Retrying failed events with max_attempts: %d", max_attempts)

            result = await session.exec(
                select(OutboxEvent)
                .where(OutboxEvent.status == "FAILED")
                .where(OutboxEvent.attempts < max_attempts)
            )
            failed_events = result.all()

            if not failed_events:
                logger.debug("No failed events found for retry")
                return 0

            logger.debug("Found %d failed events to retry", len(failed_events))

            for event in failed_events:
                event.status = "PENDING"
                event.next_run_at = datetime.now(timezone.utc)
                event.touch()
                session.add(event)
                logger.debug("Reset event %s for retry", event.id)

            await session.commit()

            logger.debug(
                "Successfully reset %d failed events for retry", len(failed_events)
            )
            return len(failed_events)

        except Exception as e:
            logger.error("Error retrying failed events: %s", str(e), exc_info=True)
            return 0

    async def cleanup_old_events(
        self, session: AsyncSession, days_old: int = 30
    ) -> int:
        """
        Clean up old completed events to prevent database bloat.

        Args:
            session (AsyncSession): Database session
            days_old (int): Number of days old events must be to be cleaned up

        Returns:
            int: Number of events cleaned up
        """
        try:
            logger.debug("Cleaning up events older than %d days", days_old)

            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)

            result = await session.exec(
                select(OutboxEvent)
                .where(OutboxEvent.status == "DONE")
                .where(OutboxEvent.updated_at < cutoff_date)
            )
            old_events = result.all()

            if not old_events:
                logger.debug("No old events found for cleanup")
                return 0

            logger.debug("Found %d old events to clean up", len(old_events))

            for event in old_events:
                await session.delete(event)

            await session.commit()

            logger.debug("Successfully cleaned up %d old events", len(old_events))
            return len(old_events)

        except Exception as e:
            logger.error("Error cleaning up old events: %s", str(e), exc_info=True)
            return 0
