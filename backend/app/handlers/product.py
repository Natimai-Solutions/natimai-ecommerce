import logging
from typing import Any

from app.outbox.decorators import outbox_handler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@outbox_handler("create.product")
async def create_notification(_session: Any, payload: dict[str, Any]) -> None:
    """Create notification."""
    logger.debug("Received product creation event with payload: %s", payload)
