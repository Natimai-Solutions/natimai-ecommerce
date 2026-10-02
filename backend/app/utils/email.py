import logging

logger = logging.getLogger(__name__)


async def send_email(user_id: str, message: str) -> None:
    """Placeholder sender: logs the message (the real senders live in
    ``app.features.notification``)."""
    logger.info("Sending email", extra={"user_id": user_id, "message": message})
