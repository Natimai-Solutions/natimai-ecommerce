"""
Regroupement de toutes les routes shipping pour faciliter l'importation.
"""

from fastapi import APIRouter

from .delivery_task import (
    delivery_task_router,
)
from .shipping_route import (
    shipping_route_router,
)
from .status import (
    status_definition_router,
    status_transition_router,
)
from .tracking import (
    consolidation_router,
    logs_router,
    shipping_route_tracking_router,
)

# Create a main shipping router
shipping_router = APIRouter(prefix="/shipping", tags=["shipping"])

# Include all sub-routers
shipping_router.include_router(shipping_route_router)
shipping_router.include_router(status_definition_router)
shipping_router.include_router(status_transition_router)
shipping_router.include_router(delivery_task_router)
shipping_router.include_router(shipping_route_tracking_router)
shipping_router.include_router(consolidation_router)
shipping_router.include_router(logs_router)

__all__ = [
    "shipping_router",
]
