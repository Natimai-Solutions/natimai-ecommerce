import logging
import socket
import sys
from typing import Any

from arq.connections import RedisSettings, create_pool
from arq.worker import func

from app.core.config import settings
from app.outbox.consumer import OUTBOX_HANDLER_MAX_TRIES, execute_outbox_handler
from app.tasks.icecat_tasks import (
    batch_enrich_products_task,
    enrich_product_with_icecat_task,
    get_enrichment_cron_jobs,
    reproject_product_specs_task,
    scheduled_batch_enrich_task,
)
from app.tasks.inventory_tasks import (
    get_stock_reservation_cron_jobs,
    release_expired_stock_reservations_task,
)
from app.tasks.pricing_tasks import (
    get_pricing_cron_jobs,
    refresh_sale_prices_task,
    scheduled_sale_price_refresh_task,
)
from app.tasks.supplier_file_import_tasks import import_supplier_file_task
from app.tasks.supplier_tasks import (
    check_supplier_health_task,
    get_supplier_sync_cron_jobs,
    scheduled_supplier_catalog_sync_task,
    scheduled_supplier_health_check_task,
    scheduled_supplier_inventory_sync_task,
    sync_supplier_inventory_task,
    sync_supplier_products_task,
)


# Custom logging filter to suppress "already running elsewhere" messages
class SuppressAlreadyRunningFilter(logging.Filter):
    """Represents suppress already running filter."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Execute filter."""
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
    """Execute example handler."""
    pass


class WorkerSettings:
    """Represents worker settings."""

    functions = [
        # Fonction générique pour les handlers outbox. `max_tries` lui est propre :
        # la politique de retry vit dans app/outbox/consumer.py et ne doit pas
        # dépendre du défaut global (qui s'applique aux tâches de sync).
        func(
            execute_outbox_handler,
            name="execute_outbox_handler",
            max_tries=OUTBOX_HANDLER_MAX_TRIES,
        ),
        example_handler,
        # Tâches fournisseurs (multi-distributeurs, liste lue en base à
        # chaque tick du planificateur)
        sync_supplier_products_task,
        sync_supplier_inventory_task,
        check_supplier_health_task,
        scheduled_supplier_catalog_sync_task,
        scheduled_supplier_inventory_sync_task,
        scheduled_supplier_health_check_task,
        # Import d'un catalogue fichier volumineux (déposé dans le stockage)
        import_supplier_file_task,
        # Tâches Icecat
        enrich_product_with_icecat_task,
        batch_enrich_products_task,
        scheduled_batch_enrich_task,
        reproject_product_specs_task,
        # Hygiène du stock : libération des réservations sans issue de paiement
        release_expired_stock_reservations_task,
        # Prix vitrine matérialisés (rafraîchis quand un taux ou une marge change)
        refresh_sale_prices_task,
        scheduled_sale_price_refresh_task,
        # ... tes autres handlers
    ]

    # Cron jobs : synchronisation fournisseurs (un jeu par fournisseur enregistré)
    # + enrichissement Icecat récurrent (drainage du backlog non-enrichi)
    # + balayage horaire des réservations de stock expirées.
    cron_jobs = (
        get_supplier_sync_cron_jobs()
        + get_enrichment_cron_jobs()
        + get_stock_reservation_cron_jobs()
        + get_pricing_cron_jobs()
    )

    # NOTE: Le polling de l'outbox est géré par un service dédié (outbox-poller)
    # pas besoin de cron job ici

    redis_settings = RedisSettings.from_dsn(str(settings.REDIS_URL))
    job_timeout = 600  # Augmenté pour les tâches de sync qui peuvent prendre du temps
    keep_result = 3600
    # Défaut pour les tâches sans politique propre (sync fournisseurs, Icecat).
    # Les handlers outbox ont le leur, cf. `functions` ci-dessus.
    max_tries = 5
    # Le worker écrit une clé de santé dans Redis à cet intervalle ; arq lui donne
    # un TTL de `interval + 1` s. À 60 s la marge était d'une seconde, donc des
    # « unhealthy » fantômes dès que la boucle prenait du retard sous charge.
    health_check_interval = 20
    # Une clé PAR CONTENEUR. La clé arq par défaut est dérivée du seul nom de
    # queue : avec `replicas: 2`, une réplique vivante rafraîchissait la clé de
    # sa jumelle morte et le healthcheck ne voyait jamais la panne. `arq --check`
    # s'exécute dans le conteneur qu'il teste, il recalcule donc le même nom.
    health_check_key = f"arq:queue:health-check:{socket.gethostname()}"
