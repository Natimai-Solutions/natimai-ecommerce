# app/scripts/outbox_poller.py
import asyncio
import logging
from datetime import datetime, timezone



from app.core.db import get_db
from app.outbox.poller import OutboxPoller

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BACKOFF = [10, 30, 60, 300]  # secondes

async def run_poller():
    """Lance le poller en continu."""
    logger.info("🚀 Starting Outbox Poller...")

    
    poller = OutboxPoller()
    
    while True:
        try:
            async with get_db() as session:
                # Traiter tous les événements pending
                await poller.process_pending_events(session)
                
                # Optionnel: retry des événements failed
                retried = await poller.retry_failed_events(session, max_attempts=5)
                if retried > 0:
                    logger.info(f"🔄 Retried {retried} failed events")
            
            # Attendre avant la prochaine itération
            await asyncio.sleep(BACKOFF[0])  # 10 secondes entre chaque poll

        except Exception as e:
            logger.error(f"❌ Error in poller: {e}")
            await asyncio.sleep(BACKOFF[1])  # 30 secondes en cas d'erreur

if __name__ == "__main__":
    asyncio.run(run_poller())