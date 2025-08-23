# app/core/outbox_poller.py
import importlib
from datetime import datetime, timedelta, timezone
from typing import Callable, Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.outbox.models import OutboxEvent
from app.outbox.registry import outbox_registry
from app.core.arq_pool import get_arq_pool

BACKOFF = [10, 30, 60, 300]  # secondes

def resolve(path: str) -> Callable[..., Any]:
    mod, func = path.split(":")
    return getattr(importlib.import_module(mod), func)

async def maybe_await(fn, *a, **k):
    res = fn(*a, **k)
    if hasattr(res, "__await__"):
        return await res
    return res

async def enqueue_jobs_for_event(event: OutboxEvent):
    """Utilise le registry au lieu du REGISTRY statique."""
    arq_pool = await get_arq_pool()
    
    # Récupérer les handlers depuis le registry
    handlers = outbox_registry.handlers.get(event.type, [])
    
    for handler in handlers:
        job_id = f"outbox:{event.id}:{handler.__name__}"
        # Enqueue le handler avec le payload
        await arq_pool.enqueue_job(
            handler.__module__ + ":" + handler.__name__, 
            **event.payload, 
            _job_id=job_id
        )

async def poll_outbox_once(session: AsyncSession) -> bool:
    """Traite un évènement PENDING dû. Retourne True si quelque chose a été fait."""
    # Sélection 1 event dû
    result = await session.exec(
        select(OutboxEvent)
        .where(OutboxEvent.status == "PENDING")
        .where(OutboxEvent.next_run_at <= datetime.now(timezone.utc))
        .order_by(OutboxEvent.created_at)
        .limit(1)
    )
    event = result.first()
    if not event:
        return False

    # Passe en RUNNING
    event.status = "RUNNING"
    event.touch()
    session.add(event)
    await session.commit()

    try:
        await enqueue_jobs_for_event(event)
        # Si tout s'est bien enqueué, on considère l'événement DONE
        event.status = "DONE"
        event.attempts += 1
        event.touch()
        session.add(event)
        await session.commit()
    except Exception as e:
        # Retry avec backoff exponentiel simple
        event.status = "PENDING"
        event.attempts += 1
        idx = min(event.attempts - 1, len(BACKOFF) - 1)
        event.next_run_at = datetime.now(timezone.utc) + timedelta(seconds=BACKOFF[idx])
        event.last_error = str(e)[:1000]
        event.touch()
        session.add(event)
        await session.commit()
    return True

class OutboxPoller:
    async def process_pending_events(self, session: AsyncSession):
        # ... code pour récupérer les événements pending
        result = await session.exec(
            select(OutboxEvent)
            .where(OutboxEvent.status == "PENDING")
            .where(OutboxEvent.next_run_at <= datetime.now(timezone.utc))
            .order_by(OutboxEvent.created_at)
        )
        pending_events = result.all()

        for event in pending_events:
            try:
                event.status = "RUNNING"
                await session.commit()
                
                # Utiliser le registry pour traiter l'événement
                success = await outbox_registry.process_event(session, event)
                
                if success:
                    event.status = "DONE"
                else:
                    event.status = "FAILED"
                    event.attempts += 1
                
                event.touch()
                await session.commit()
                
            except Exception as e:
                event.status = "FAILED"
                event.attempts += 1
                event.error_message = str(e)
                event.touch()
                await session.commit()
