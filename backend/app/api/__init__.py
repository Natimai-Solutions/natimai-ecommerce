from fastapi import APIRouter

api_router = APIRouter()

from app.api.routes.address import router as address_router
from app.api.routes.login import router as login_router
from app.api.routes.partner import router as partner_router
from app.api.routes.payment_method import (
    router as payment_method_router,
)
from app.api.routes.place import router as place_router
from app.api.routes.product import (
    router as product_router,
)
from app.api.routes.shipping import shipping_router
from app.api.routes.user_notification import (
    router as user_notification_router,
)
from app.api.routes.user_review import (
    router as user_review_router,
)
from app.api.routes.user_wishlist import router as user_wishlist_router
from app.api.routes.utils import router as utils_router

# api_router.include_router(payment_router, prefix="/payment", tags=["payment"])
api_router.include_router(login_router, tags=["login"])
api_router.include_router(partner_router)
api_router.include_router(place_router)
api_router.include_router(payment_method_router)
api_router.include_router(product_router)

# api_router.include_router(payment_router, prefix="/payment", tags=["payment"])
api_router.include_router(address_router, prefix="/users", tags=["addresses"])
api_router.include_router(user_review_router, prefix="/reviews", tags=["reviews"])
api_router.include_router(
    user_notification_router, prefix="/notifications", tags=["notifications"]
)
api_router.include_router(user_wishlist_router, prefix="/wishlist", tags=["wishlist"])
api_router.include_router(utils_router, prefix="/utils", tags=["utils"])

# Shipping routes
api_router.include_router(shipping_router)
