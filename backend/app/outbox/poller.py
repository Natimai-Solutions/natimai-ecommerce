# app/core/outbox_poller.py
import importlib
from datetime import datetime, timedelta, timezone
from typing import Callable, Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.outbox.models import OutboxEvent, OutboxStatus
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
    """Utilise le registry pour envoyer les handlers vers ARQ."""
    arq_pool = await get_arq_pool()
    
    # Récupérer les handlers depuis le registry
    handlers = outbox_registry.handlers.get(event.type, [])
    
    if not handlers:
        raise Exception(f"No handlers found for event type: {event.type}")
    
    for handler in handlers:
        job_id = f"outbox:{event.id}:{handler.__name__}"
        handler_path = f"{handler.__module__}:{handler.__name__}"
        
        # Enqueue le handler avec le payload
        await arq_pool.enqueue_job(
            handler_path,
            **event.payload,
            _job_id=job_id
        )

async def poll_outbox_once(session: AsyncSession) -> bool:
    """Traite un évènement PENDING dû. Retourne True si quelque chose a été fait."""
    # Sélection 1 event dû
    result = await session.exec(
        select(OutboxEvent)
        .where(OutboxEvent.status == OutboxStatus.PENDING)
        .where(OutboxEvent.next_run_at <= datetime.now(timezone.utc))
        .order_by(OutboxEvent.created_at)
        .limit(1)
    )
    event = result.first()
    if not event:
        return False

    # Passe en RUNNING
    event.status = OutboxStatus.RUNNING
    event.touch()
    session.add(event)
    await session.commit()

    try:
        await enqueue_jobs_for_event(event)
        # Si tout s'est bien enqueué, on considère l'événement DONE
        event.status = OutboxStatus.DONE
        event.attempts += 1
        event.touch()
        session.add(event)
        await session.commit()
    except Exception as e:
        # Retry avec backoff exponentiel simple
        event.status = OutboxStatus.PENDING
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
        """Traite tous les événements pending en les envoyant vers ARQ."""
        arq_pool = await get_arq_pool()
        
        # Récupérer tous les événements pending dus
        result = await session.exec(
            select(OutboxEvent)
            .where(OutboxEvent.status == OutboxStatus.PENDING)
            .where(OutboxEvent.next_run_at <= datetime.now(timezone.utc))
            .order_by(OutboxEvent.created_at)
        )
        pending_events = result.all()

        for event in pending_events:
            try:
                # Marquer comme RUNNING
                event.status = OutboxStatus.RUNNING
                event.touch()
                session.add(event)
                await session.commit()
                
                # Récupérer les handlers pour cet événement
                handlers = outbox_registry.handlers.get(event.type, [])
                
                if not handlers:
                    raise Exception(f"No handlers found for event type: {event.type}")
                
                # Envoyer chaque handler vers ARQ
                for handler in handlers:
                    job_id = f"outbox:{event.id}:{handler.__name__}"
                    handler_path = f"{handler.__module__}:{handler.__name__}"
                    
                    await arq_pool.enqueue_job(
                        handler_path,
                        **event.payload,
                        _job_id=job_id
                    )
                
                # Marquer comme DONE si tout s'est bien passé
                event.status = OutboxStatus.DONE
                event.attempts += 1
                event.touch()
                session.add(event)
                await session.commit()
                
            except Exception as e:
                # Gérer l'échec avec backoff
                event.status = OutboxStatus.PENDING
                event.attempts += 1
                idx = min(event.attempts - 1, len(BACKOFF) - 1)
                event.next_run_at = datetime.now(timezone.utc) + timedelta(seconds=BACKOFF[idx])
                event.last_error = str(e)[:1000]
                event.touch()
                session.add(event)
                await session.commit()

    async def process_single_event(self, session: AsyncSession, event_id: str) -> bool:
        """Traite un événement spécifique par son ID."""
        result = await session.exec(
            select(OutboxEvent).where(OutboxEvent.id == event_id)
        )
        event = result.first()
        
        if not event:
            return False
            
        if event.status != OutboxStatus.PENDING:
            return False
            
        try:
            event.status = OutboxStatus.RUNNING
            event.touch()
            session.add(event)
            await session.commit()
            
            await enqueue_jobs_for_event(event)
            
            event.status = OutboxStatus.DONE
            event.attempts += 1
            event.touch()
            session.add(event)
            await session.commit()
            return True
            
        except Exception as e:
            event.status = OutboxStatus.PENDING
            event.attempts += 1
            idx = min(event.attempts - 1, len(BACKOFF) - 1)
            event.next_run_at = datetime.now(timezone.utc) + timedelta(seconds=BACKOFF[idx])
            event.last_error = str(e)[:1000]
            event.touch()
            session.add(event)
            await session.commit()
            return False

    async def retry_failed_events(self, session: AsyncSession, max_attempts: int = 5):
        """Remettre en PENDING les événements FAILED qui n'ont pas dépassé le max d'attempts."""
        result = await session.exec(
            select(OutboxEvent)
            .where(OutboxEvent.status == OutboxStatus.FAILED)
            .where(OutboxEvent.attempts < max_attempts)
        )
        failed_events = result.all()
        
        for event in failed_events:
            event.status = OutboxStatus.PENDING
            event.next_run_at = datetime.now(timezone.utc)
            event.touch()
            session.add(event)
            
        await session.commit()
        return len(failed_events)
