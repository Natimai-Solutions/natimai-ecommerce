import logging
from app.outbox.decorators import outbox_handler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@outbox_handler("create.product")
async def create_notification(session, payload) -> None:
    logger.info("Received product creation event with payload: %s", payload)