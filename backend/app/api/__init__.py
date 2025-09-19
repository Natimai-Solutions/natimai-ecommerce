from fastapi import APIRouter

api_router = APIRouter()

from app.api.routes.login import router as login_router

# from app.api.routes.payment import router as payment_router
from app.api.routes.payment_method import (
    router as payment_method_router,
)
from app.api.routes.product import (
    router as product_router,
)

# from app.api.routes.shipping_method import (
#    router as shipping_method_router,
# )
# from app.api.routes.shipping_status import (
#    router as shipping_status_router,
# )
from app.api.routes.shipping_zone import (
    router as shipping_zone_router,
)
from app.api.routes.utils import router as utils_router

# api_router.include_router(payment_router, prefix="/payment", tags=["payment"])
api_router.include_router(login_router, tags=["login"])
api_router.include_router(payment_method_router)
api_router.include_router(product_router)
# api_router.include_router(shipping_method_router, prefix="/shipping", tags=["shipping"])
# api_router.include_router(shipping_status_router, prefix="/shipping-status", tags=["shipping"])
api_router.include_router(shipping_zone_router)
api_router.include_router(utils_router, prefix="/utils", tags=["utils"])
