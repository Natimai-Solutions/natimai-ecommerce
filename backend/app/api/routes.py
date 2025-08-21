import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.tasks import celery_app

# Import module routers (only those that currently define a router)
from app.api.routes.payment_route import router as payment_router
from app.api.routes.payment_method_route import (
    router as payment_method_router,
)
from app.api.routes.shipping_method_route import (
    router as shipping_method_router,
)
from app.api.routes.shipping_status_route import (
    router as shipping_status_router,
)
from app.api.routes.shipping_zone_route import (
    router as shipping_zone_router,
)


api_router = APIRouter()


# Utils endpoints
@api_router.get("/utils/health-check", tags=["utils"])
async def health_check() -> bool:
    return True


class TaskStatus(BaseModel):
    task_id: uuid.UUID
    finished: bool
    success: bool
    state: str


@api_router.get(
    "/utils/task-check/{task_id}", tags=["utils"], response_model=TaskStatus
)
async def check_tasks(
    task_id: uuid.UUID,
) -> TaskStatus:
    task = celery_app.AsyncResult(str(task_id))
    return TaskStatus(
        task_id=task_id,
        finished=task.ready(),
        success=task.successful(),
        state=task.state,
    )


# Mount module routers with prefixes and tags
api_router.include_router(payment_method_router, prefix="/payment-method", tags=["payment"])
api_router.include_router(payment_router, prefix="/payment", tags=["payment"])

api_router.include_router(shipping_method_router, prefix="/shipping", tags=["shipping"])
api_router.include_router(shipping_status_router, prefix="/shipping-status", tags=["shipping"])
api_router.include_router(shipping_zone_router, prefix="/shipping-zone", tags=["shipping"])

# Placeholders (uncomment when routers exist)
# from app.api.product.routes.product import router as product_router
# api_router.include_router(product_router, prefix="/products", tags=["product"])
# from app.api.order.routes.order_status_route import router as order_router
# api_router.include_router(order_router, prefix="/orders", tags=["order"])
# from app.api.user.routes.user_route import router as user_router
# api_router.include_router(user_router, prefix="/users", tags=["user"])
