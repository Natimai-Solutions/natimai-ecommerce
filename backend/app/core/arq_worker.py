import importlib
import logging

from arq.connections import RedisSettings
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.db import engine

logger = logging.getLogger(__name__)


# Fonction générique pour résoudre et exécuter les handlers outbox
async def execute_outbox_handler(ctx, handler_path: str, **kwargs):
    """
    Résout et exécute un handler outbox depuis son chemin de module.

    Args:
        ctx: Contexte ARQ
        handler_path: Chemin du handler au format "module.path:function_name"
        **kwargs: Arguments à passer au handler
    """
    try:
        # Résoudre le handler depuis le chemin
        mod, func = handler_path.split(":")
        module = importlib.import_module(mod)
        handler = getattr(module, func)

        logger.info("Executing handler %s with kwargs: %s", handler_path, kwargs)

        # Créer une session de base de données
        async with AsyncSession(engine) as session:
            # Exécuter le handler avec la session et les kwargs
            await handler(session, kwargs)

        logger.info("Successfully executed handler %s", handler_path)

    except Exception as e:
        logger.error("Failed to execute handler %s: %s", handler_path, str(e))
        raise


# Tes handlers ARQ existants
async def example_handler(ctx, **kwargs):
    # ... logique du handler
    pass


class WorkerSettings:
    functions = [
        execute_outbox_handler,  # Fonction générique pour les handlers outbox
        example_handler,
        # ... tes autres handlers
    ]

    # Configuration des retries ARQ pour les handlers individuels
    max_tries = 3  # 3 tentatives par handler
    retry_delay = 10  # 10 secondes entre les tentatives ARQ
    job_timeout = 300  # 5 minutes timeout par job
    keep_result = 3600  # Garde les résultats 1 heure pour debugging

    # NOTE: Le polling de l'outbox est géré par un service dédié (outbox-poller)
    # L'outbox gère l'orchestration, ARQ gère les retries des handlers individuels

    redis_settings = RedisSettings.from_dsn(str(settings.REDIS_URL))
