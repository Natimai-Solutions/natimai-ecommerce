"""Payment sweeps run by the ARQ worker (R8 / confort).

The authorisation expiry alert: once a day, warn about card authorisations
that will expire unused (see ``features/payment/services/authorizations``).
"""

from __future__ import annotations

import logging
from typing import Any

from arq import cron
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import engine
from app.features.payment.services.authorizations import (
    alert_expiring_authorizations,
)

logger = logging.getLogger(__name__)


async def alert_expiring_authorizations_task(_ctx: dict[str, Any]) -> dict[str, int]:
    """Daily: one ops alert per authorisation about to expire without capture."""
    async with AsyncSession(engine) as session:
        stats = await alert_expiring_authorizations(session)
    logger.info("Authorization expiry sweep: %s", stats)
    return stats


def get_payment_cron_jobs() -> list[Any]:
    """07:00 UTC — before the day's shipments, after the night's IPNs."""
    return [
        cron(
            alert_expiring_authorizations_task,  # type: ignore[arg-type]
            hour=7,
            minute=0,
            second=0,
            name="authorization_expiry_alert",
        )
    ]
