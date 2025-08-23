from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Dict, List
from sqlmodel.ext.asyncio.session import AsyncSession
from .models import OutboxEvent

class OutboxRegistry:
    def __init__(self):
        self.handlers: Dict[str, List[Callable]] = {}

    async def publish(
        self, 
        session: AsyncSession, 
        event_type: str, 
        payload: Dict[str, Any],
        delay_seconds: int = 0
    ) -> OutboxEvent:
        """Publier un événement dans l'outbox."""
        next_run_at = datetime.now(timezone.utc)
        if delay_seconds > 0:
            next_run_at += timedelta(seconds=delay_seconds)
            
        event = OutboxEvent(
            type=event_type,
            payload=payload,
            next_run_at=next_run_at
        )
        session.add(event)
        await session.flush()  # Pour récupérer l'ID
        return event

    def register_handler(self, event_type: str, handler: Callable):
        """Enregistrer un handler directement."""
        if event_type not in self.handlers:
            self.handlers[event_type] = []
        self.handlers[event_type].append(handler)

# Instance globale
outbox_registry = OutboxRegistry()

