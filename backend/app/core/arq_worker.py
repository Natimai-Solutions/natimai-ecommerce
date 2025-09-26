from arq.connections import RedisSettings

from app.core.config import settings


# Tes handlers ARQ existants
async def example_handler(ctx, **kwargs):
    # ... logique du handler
    pass


class WorkerSettings:
    functions = [
        example_handler,
        # ... tes autres handlers
    ]

    # NOTE: Le polling de l'outbox est géré par un service dédié (outbox-poller)
    # pas besoin de cron job ici

    redis_settings = RedisSettings.from_dsn(str(settings.REDIS_URL))
    job_timeout = 300
    keep_result = 3600
