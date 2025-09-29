from fastapi import APIRouter

api_router = APIRouter()

#from app.api.routes.payment import router as payment_router
from app.api.routes.address import router as address_router
from app.api.routes.payment_method import (
    router as payment_method_router,
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
from app.api.routes.user_review import (
    router as user_review_router,
)
from app.api.routes.user_notification import (
    router as user_notification_router,
)
from app.api.routes.utils import router as utils_router
from app.api.routes.wishlist import router as wishlist_router

#api_router.include_router(payment_router, prefix="/payment", tags=["payment"])
api_router.include_router(address_router, prefix="/users", tags=["addresses"])
api_router.include_router(payment_method_router)
# api_router.include_router(shipping_method_router, prefix="/shipping", tags=["shipping"])
# api_router.include_router(shipping_status_router, prefix="/shipping-status", tags=["shipping"])
api_router.include_router(shipping_zone_router)
api_router.include_router(user_review_router, prefix="/reviews", tags=["reviews"])
api_router.include_router(
    user_notification_router, prefix="/notifications", tags=["notifications"]
)
api_router.include_router(utils_router, prefix="/utils", tags=["utils"])
api_router.include_router(wishlist_router, prefix="/wishlist", tags=["wishlist"])
