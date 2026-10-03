"""
Outbox Registry for event management.

This module provides the central registry for managing outbox events and their handlers.
The OutboxRegistry class manages event publication and handler registration for the
outbox pattern implementation.
"""

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from .models import OutboxEvent

logger = logging.getLogger(__name__)

Handler = Callable[..., Any]


class OutboxRegistry:
    """
    Central registry for outbox events and handlers.

    This class manages the registration of event handlers and provides methods
    for publishing events to the outbox. It maintains a mapping of event types
    to their corresponding handler functions.

    Attributes:
        handlers (Dict[str, List[Callable]]): Mapping of event types to handler functions
        model_classes (Dict[str, Type[Any]]): Mapping of event types to model classes
    """

    def __init__(self) -> None:
        """Initialize the outbox registry instance."""
        self.handlers: dict[str, list[Handler]] = {}
        self.model_classes: dict[str, type[Any]] = {}
        logger.debug("Initialized OutboxRegistry")

    async def publish(
        self,
        session: AsyncSession,
        event_type: str,
        payload: dict[str, Any],
        delay_seconds: int = 0,
        correlation_id: str | uuid.UUID | None = None,
    ) -> OutboxEvent:
        """
        Publish an event to the outbox.

        This method creates a new outbox event with the specified parameters
        and adds it to the database session. The event will be processed
        by the outbox poller according to its scheduled run time.

        Args:
            session (AsyncSession): Database session for persisting the event
            event_type (str): Type/name of the event to publish
            payload (Dict[str, Any]): Event data payload
            delay_seconds (int, optional): Delay before processing the event. Defaults to 0.
            correlation_id (str | UUID, optional): ID for tracking related events

        Returns:
            OutboxEvent: The created outbox event

        Example:
            event = await registry.publish(
                session=db_session,
                event_type="user.created",
                payload={"user_id": 123, "email": "user@example.com"},
                delay_seconds=10
            )

        Raises:
            Exception: If event creation or database operation fails
        """
        try:
            logger.debug(
                "Publishing event type: %s with payload keys: %s",
                event_type,
                list(payload.keys()),
            )

            next_run_at = datetime.now(UTC)
            if delay_seconds > 0:
                next_run_at += timedelta(seconds=delay_seconds)
                logger.debug(
                    "Event scheduled for delayed processing: %s seconds", delay_seconds
                )

            correlation_uuid: uuid.UUID | None
            if correlation_id is None:
                correlation_uuid = None
            elif isinstance(correlation_id, uuid.UUID):
                correlation_uuid = correlation_id
            else:
                correlation_uuid = uuid.UUID(correlation_id)

            event = OutboxEvent(
                type=event_type,
                payload=payload,
                next_run_at=next_run_at,
                correlation_id=correlation_uuid,
            )
            session.add(event)
            await session.flush()  # To get the ID

            logger.debug(
                "Successfully published event: %s (ID: %s)", event_type, event.id
            )
            return event

        except Exception as e:
            logger.error(
                "Failed to publish event %s: %s", event_type, str(e), exc_info=True
            )
            raise

    def register_handler(
        self,
        event_type: str,
        handler: Handler,
        model_class: type[Any] | None = None,
    ) -> None:
        """
        Register a handler function for a specific event type.

        This method adds a handler function to the registry for the specified event type.
        Multiple handlers can be registered for the same event type, and they will all
        be executed when an event of that type is processed.

        Args:
            event_type (str): The type of event this handler processes
            handler (Callable): The handler function to register
            model_class (Type[Any], optional): The model class associated with this event

        Example:
            registry.register_handler("user.created", handle_user_created, User)

        Raises:
            Exception: If handler registration fails
        """
        try:
            if event_type not in self.handlers:
                self.handlers[event_type] = []
                logger.debug("Created new handler list for event type: %s", event_type)

            self.handlers[event_type].append(handler)

            if model_class:
                self.model_classes[event_type] = model_class
                logger.debug(
                    "Associated model class %s with event type: %s",
                    model_class.__name__,
                    event_type,
                )

            logger.debug(
                "Registered handler %s for event type: %s", handler.__name__, event_type
            )

        except Exception as e:
            logger.error("Failed to register handler for %s: %s", event_type, str(e))
            raise

    def get_handlers(self, event_type: str) -> list[Handler]:
        """
        Get all registered handlers for a specific event type.

        Args:
            event_type (str): The event type to get handlers for

        Returns:
            List[Callable]: List of handler functions for the event type
        """
        handlers = self.handlers.get(event_type, [])
        logger.debug(
            "Retrieved %d handlers for event type: %s", len(handlers), event_type
        )
        return handlers

    def get_model_class(self, event_type: str) -> type[Any] | None:
        """
        Get the model class associated with an event type.

        Args:
            event_type (str): The event type to get the model class for

        Returns:
            Optional[Type[Any]]: The model class if registered, None otherwise
        """
        return self.model_classes.get(event_type)

    def list_event_types(self) -> list[str]:
        """
        Get a list of all registered event types.

        Returns:
            List[str]: List of all event types with registered handlers
        """
        event_types = list(self.handlers.keys())
        logger.debug("Listed %d registered event types", len(event_types))
        return event_types

    def handler_count(self, event_type: str | None = None) -> int:
        """
        Get the count of handlers for a specific event type or all event types.

        Args:
            event_type (str, optional): Specific event type to count. If None, counts all.

        Returns:
            int: Number of handlers
        """
        if event_type:
            return len(self.handlers.get(event_type, []))
        else:
            return sum(len(handlers) for handlers in self.handlers.values())

    def clear_handlers(self, event_type: str | None = None) -> None:
        """
        Clear handlers for a specific event type or all event types.

        Args:
            event_type (str, optional): Specific event type to clear. If None, clears all.
        """
        if event_type:
            if event_type in self.handlers:
                del self.handlers[event_type]
                if event_type in self.model_classes:
                    del self.model_classes[event_type]
                logger.debug("Cleared handlers for event type: %s", event_type)
        else:
            self.handlers.clear()
            self.model_classes.clear()
            logger.debug("Cleared all handlers")


# Global instance
outbox_registry = OutboxRegistry()
logger.debug("Initialized global outbox registry instance")
