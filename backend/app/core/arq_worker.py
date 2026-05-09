import logging
import sys
from typing import Any

from arq.connections import RedisSettings, create_pool

from app.core.config import settings
from app.outbox.consumer import execute_outbox_handler
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
    def filter(self, record: logging.LogRecord) -> bool:
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
async def get_redis_pool() -> Any:
    """Get Redis pool for ARQ job enqueuing"""
    return await create_pool(RedisSettings.from_dsn(str(settings.REDIS_URL)))


# Tes handlers ARQ existants
async def example_handler(_ctx: dict[str, Any], **_kwargs: Any) -> None:
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
