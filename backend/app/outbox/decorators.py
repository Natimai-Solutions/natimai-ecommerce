"""
Decorators for Outbox pattern event handlers.

This module provides decorators for registering event handlers with the OutboxRegistry.
Event handlers are automatically discovered and registered during application startup.
"""

import logging
from collections.abc import Callable
from functools import wraps
from typing import Any

from app.outbox.registry import outbox_registry

logger = logging.getLogger(__name__)

Handler = Callable[..., Any]


def outbox_handler(
    event_type: str,
    model_class: type[Any] | None = None,
) -> Callable[[Handler], Handler]:
    """
    Decorator to register a function as an outbox event handler.

    This decorator registers a function to handle specific outbox events.
    The decorated function will be automatically called when events of the
    specified type are processed by the outbox poller.

    Args:
        event_type (str): The type of event this handler processes
        model_class (Type[Any], optional): The model class associated with this event type

    Example:
        @outbox_handler("user.created", User)
        async def handle_user_created(event_data: dict, context: dict = None):
            logger.debug(f"Processing user creation: {event_data}")
            # Send welcome email, create user profile, etc.

    Returns:
        Callable: The decorated function
    """

    def decorator(func: Handler) -> Handler:
        """Wrap and register a single-event handler."""

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            """Execute wrapper."""
            try:
                logger.debug(f"Executing handler for event type: {event_type}")
                result = await func(*args, **kwargs)
                logger.debug(f"Handler for {event_type} completed successfully")
                return result
            except Exception as e:
                logger.error(
                    f"Error in handler for {event_type}: {str(e)}", exc_info=True
                )
                raise

        # Register the handler with the OutboxRegistry
        try:
            outbox_registry.register_handler(event_type, wrapper, model_class)
            logger.debug(f"Registered outbox handler for event type: {event_type}")
        except Exception as e:
            logger.error(f"Failed to register handler for {event_type}: {str(e)}")
            raise

        return wrapper

    return decorator


def bulk_outbox_handler(
    event_types: list[str],
    model_class: type[Any] | None = None,
) -> Callable[[Handler], Handler]:
    """
    Decorator to register a function as a handler for multiple outbox event types.

    This decorator allows a single function to handle multiple event types.
    Useful for handlers that process similar events or perform batch operations.

    Args:
        event_types (list[str]): List of event types this handler processes
        model_class (Type[Any], optional): The model class associated with these event types

    Example:
        @bulk_outbox_handler(["user.created", "user.updated"], User)
        async def handle_user_changes(event_data: dict, context: dict = None):
            logger.debug(f"Processing user change: {event_data}")
            # Update search index, sync with external services, etc.

    Returns:
        Callable: The decorated function
    """

    def decorator(func: Handler) -> Handler:
        """Wrap and register a multi-event handler."""

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            """Execute wrapper."""
            try:
                logger.debug(f"Executing bulk handler for event types: {event_types}")
                result = await func(*args, **kwargs)
                logger.debug("Bulk handler completed successfully")
                return result
            except Exception as e:
                logger.error(f"Error in bulk handler: {str(e)}", exc_info=True)
                raise

        # Register the handler for each event type
        for event_type in event_types:
            try:
                outbox_registry.register_handler(event_type, wrapper, model_class)
                logger.debug(f"Registered bulk handler for event type: {event_type}")
            except Exception as e:
                logger.error(
                    f"Failed to register bulk handler for {event_type}: {str(e)}"
                )
                raise

        return wrapper

    return decorator
