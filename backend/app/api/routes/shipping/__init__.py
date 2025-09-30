"""
Regroupement de toutes les routes shipping pour faciliter l'importation.
"""

from fastapi import APIRouter

# Import all shipping routers
from .partner import router as partner_router
from .place import router as place_router
from .route import (
    shipping_route_router,
    shipping_route_step_router,
)
from .consolidation import (
    route_consolidation_router,
    order_consolidation_router,
    order_step_consolidation_router,
)
from .status import (
    status_definition_router,
    status_transition_router,
)
from .tracking import (
    tracking_event_router,
)
from .delivery import (
    delivery_task_router,
    package_router,
)

# Create a main shipping router
shipping_router = APIRouter(prefix="/shipping", tags=["shipping"])

# Include all sub-routers
shipping_router.include_router(partner_router)
shipping_router.include_router(place_router)
shipping_router.include_router(shipping_route_router)
shipping_router.include_router(shipping_route_step_router)
shipping_router.include_router(route_consolidation_router)
shipping_router.include_router(order_consolidation_router)
shipping_router.include_router(status_definition_router)
shipping_router.include_router(status_transition_router)
shipping_router.include_router(tracking_event_router)
shipping_router.include_router(order_step_consolidation_router)
shipping_router.include_router(delivery_task_router)
shipping_router.include_router(package_router)

__all__ = [
    "shipping_router",
    "partner_router",
    "place_router",
    "shipping_route_router",
    "shipping_route_step_router",
    "route_consolidation_router",
    "order_consolidation_router",
    "status_definition_router",
    "status_transition_router",
    "tracking_event_router",
    "order_step_consolidation_router",
    "delivery_task_router",
    "package_router",
]