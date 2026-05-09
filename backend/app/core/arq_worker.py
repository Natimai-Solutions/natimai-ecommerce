import importlib
import logging
import sys

from arq.connections import RedisSettings, create_pool
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.db import engine
from app.tasks.icecat_tasks import (
    batch_enrich_products_task,
    enrich_product_with_icecat_task,
)
from app.tasks.ingram_micro_tasks import (
    check_ingram_api_health_task,
    get_ingram_sync_cron_jobs,
    sync_ingram_inventory_task,
    sync_ingram_products_task,
)


# Custom logging filter to suppress "already running elsewhere" messages
class SuppressAlreadyRunningFilter(logging.Filter):
    def filter(self, record):
        return "already running elsewhere" not in record.getMessage()


# Configure logging for the worker
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s:%(message)s",
    stream=sys.stdout,
    force=True,  # Override any existing configuration
)

# Add filter to suppress noisy "already running elsewhere" messages
# These are normal when using custom job IDs and indicate deduplication is working
arq_logger = logging.getLogger("arq.worker")
arq_logger.addFilter(SuppressAlreadyRunningFilter())

logger = logging.getLogger(__name__)


# Redis pool pour ARQ
async def get_redis_pool():
    """Get Redis pool for ARQ job enqueuing"""
    return await create_pool(RedisSettings.from_dsn(str(settings.REDIS_URL)))


# Fonction générique pour résoudre et exécuter les handlers outbox
async def execute_outbox_handler(_ctx, handler_path: str, **kwargs):
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

        logger.debug("Executing handler %s with kwargs: %s", handler_path, kwargs)

        # Créer une session de base de données
        async with AsyncSession(engine) as session:
            # Exécuter le handler avec la session et les kwargs
            await handler(session, kwargs)

        logger.debug("Successfully executed handler %s", handler_path)

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
        # Tâches Ingram Micro
        sync_ingram_products_task,
        sync_ingram_inventory_task,
        check_ingram_api_health_task,
        # Tâches Icecat
        enrich_product_with_icecat_task,
        batch_enrich_products_task,
        # ... tes autres handlers
    ]

    # Cron jobs pour la synchronisation planifiée
    cron_jobs = get_ingram_sync_cron_jobs()

    # NOTE: Le polling de l'outbox est géré par un service dédié (outbox-poller)
    # pas besoin de cron job ici

    redis_settings = RedisSettings.from_dsn(str(settings.REDIS_URL))
    job_timeout = 600  # Augmenté pour les tâches de sync qui peuvent prendre du temps
    keep_result = 3600
