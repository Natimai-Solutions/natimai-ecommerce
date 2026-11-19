"""Brand sheets (chantier accueil et messagerie, lot BR): every hour, the
products imported or edited without a brand are linked to their sheet."""

from __future__ import annotations

import logging
from typing import Any

from arq import cron
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import engine
from app.features.product.services.brands import link_unbranded_products

logger = logging.getLogger(__name__)


async def link_product_brands_task(
    _ctx: dict[str, Any], **_kwargs: Any
) -> dict[str, Any]:
    async with AsyncSession(engine) as session:
        linked = await link_unbranded_products(session)
    if linked:
        logger.info("Brand sheets: %d product(s) linked", linked)
    return {"status": "ok", "linked": linked}


def get_brand_cron_jobs() -> list[Any]:
    return [
        cron(
            link_product_brands_task,  # type: ignore[arg-type]
            minute={17},
            second=0,
            name="link_product_brands",
        )
    ]
