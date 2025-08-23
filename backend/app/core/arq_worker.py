from arq.connections import RedisSettings

from app.core.db import get_db
from app.outbox.poller import poll_outbox_once

# Tes handlers ARQ existants
async def example_handler(ctx, **kwargs):
    # ... logique du handler
    pass

# Tâche de background pour le poller
async def outbox_poller_task(ctx):
    """Tâche ARQ qui poll l'outbox périodiquement."""
    async with get_db() as session:
        processed = False
        # Traiter jusqu'à ce qu'il n'y ait plus d'événements
        while await poll_outbox_once(session):
            processed = True
        
        if processed:
            ctx['logger'].info("Outbox events processed")

class WorkerSettings:
    functions = [
        example_handler,
        # ... tes autres handlers
    ]
    
    # Tâche cron pour le poller outbox
    cron_jobs = [
        {
            'function': outbox_poller_task,
            'cron': '* * * * *',  # Chaque minute
        }
    ]
    
    redis_settings = RedisSettings.from_dsn('redis://localhost:6379')
    job_timeout = 300
    keep_result = 3600