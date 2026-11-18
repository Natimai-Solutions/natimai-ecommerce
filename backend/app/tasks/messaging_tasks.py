"""Messaging tasks (chantier accueil et messagerie, lot MSG1): the e-mails
about unread messages every five minutes, and every morning the release of
conversations held without an answer."""

from __future__ import annotations

import logging
from typing import Any

from arq import cron
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import engine
from app.features.messaging.notify import notify_unread, release_stale
from app.features.messaging.retention import retention_sweep
from app.features.system.modules import module_enabled

logger = logging.getLogger(__name__)


async def notify_unread_messages_task(
    _ctx: dict[str, Any], **_kwargs: Any
) -> dict[str, Any]:
    """One notice per wave of unread messages, customer side and team side."""
    async with AsyncSession(engine) as session:
        if not await module_enabled(session, "messaging"):
            return {"status": "disabled"}
        sent = await notify_unread(session)
    return {"status": "ok", **sent}


async def release_stale_conversations_task(
    _ctx: dict[str, Any], **_kwargs: Any
) -> dict[str, Any]:
    """Conversations held for days without an answer go back to the queue."""
    async with AsyncSession(engine) as session:
        if not await module_enabled(session, "messaging"):
            return {"status": "disabled"}
        released = await release_stale(session)
    logger.info("Messaging: %s conversation(s) released", released)
    return {"status": "ok", "released": released}


async def messaging_retention_task(
    _ctx: dict[str, Any], **_kwargs: Any
) -> dict[str, Any]:
    """Deletion notices, then deletions (runs even with the module off: the
    retention promise holds for conversations already written)."""
    async with AsyncSession(engine) as session:
        result = await retention_sweep(session)
    return {"status": "ok", **result}


def get_messaging_cron_jobs() -> list[Any]:
    """Every five minutes; the release at 07:20 in Tahiti (17:20 UTC); the
    retention at 03:40 in Tahiti (13:40 UTC)."""
    return [
        cron(
            notify_unread_messages_task,  # type: ignore[arg-type]
            minute=set(range(1, 60, 5)),
            second=30,
            name="notify_unread_messages",
        ),
        cron(
            release_stale_conversations_task,  # type: ignore[arg-type]
            hour=17,
            minute=20,
            second=0,
            name="release_stale_conversations",
        ),
        cron(
            messaging_retention_task,  # type: ignore[arg-type]
            hour=13,
            minute=40,
            second=0,
            name="messaging_retention",
        ),
    ]
