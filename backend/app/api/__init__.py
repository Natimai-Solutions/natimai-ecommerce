from fastapi import APIRouter

from app.api.routes.address import router as address_router
from app.api.routes.admin_carts import router as admin_carts_router
from app.api.routes.admin_categories import router as admin_categories_router
from app.api.routes.admin_credit_notes import router as admin_credit_notes_router
from app.api.routes.admin_currency_rates import router as admin_currency_rates_router
from app.api.routes.admin_grouped_departures import (
    router as admin_grouped_departures_router,
)
from app.api.routes.admin_inventory import router as admin_inventory_router
from app.api.routes.admin_invoices import router as admin_invoices_router
from app.api.routes.admin_orders import router as admin_orders_router
from app.api.routes.admin_payment_eligibility import (
    router as admin_payment_eligibility_router,
)
from app.api.routes.admin_payments import router as admin_payments_router
from app.api.routes.admin_price_groups import router as admin_price_groups_router
from app.api.routes.admin_product import router as admin_product_router
from app.api.routes.admin_quote_requests import router as admin_quote_requests_router
from app.api.routes.admin_shipping import router as admin_shipping_router
from app.api.routes.admin_spec_definitions import (
    router as admin_spec_definitions_router,
)
from app.api.routes.admin_supplier_orders import (
    router as admin_supplier_orders_router,
)
from app.api.routes.admin_suppliers import router as admin_suppliers_router
from app.api.routes.admin_tax_rates import router as admin_tax_rates_router
from app.api.routes.admin_users import router as admin_users_router
from app.api.routes.analytics_product import router as analytics_product_router
from app.api.routes.analytics_sale import router as analytics_sale_router
from app.api.routes.analytics_user import router as analytics_user_router
from app.api.routes.brand import router as brand_router
from app.api.routes.cart import router as cart_router
from app.api.routes.category import router as category_router
from app.api.routes.content_pages import router as content_pages_router
from app.api.routes.currency import router as currency_router
from app.api.routes.discount import router as discount_router
from app.api.routes.group import router as group_router
from app.api.routes.group_security import router as group_security_router
from app.api.routes.group_upgrade import router as group_upgrade_router
from app.api.routes.grouped_departures import router as grouped_departures_router
from app.api.routes.health import router as health_router
from app.api.routes.homepage import router as homepage_router
from app.api.routes.icecat import router as icecat_router
from app.api.routes.internal_storage import router as internal_storage_router
from app.api.routes.inventory import router as inventory_router
from app.api.routes.invoices_me import router as invoices_me_router
from app.api.routes.login import router as login_router
from app.api.routes.media import router as media_router
from app.api.routes.oauth import router as oauth_router
from app.api.routes.order import router as order_router
from app.api.routes.order_line import router as order_line_router
from app.api.routes.order_status import router as order_status_router
from app.api.routes.orders_me import router as orders_me_router
from app.api.routes.partner import router as partner_router
from app.api.routes.password_reset import router as password_reset_router
from app.api.routes.payment import router as payment_router
from app.api.routes.payment_method import (
    router as payment_method_router,
)
from app.api.routes.payments import router as payments_router
from app.api.routes.place import router as place_router
from app.api.routes.product import (
    router as product_router,
)
from app.api.routes.product_catalog import router as product_catalog_router
from app.api.routes.shipping import shipping_router
from app.api.routes.signup import router as signup_router
from app.api.routes.stock_alerts import router as stock_alerts_router
from app.api.routes.stock_movement import router as stock_movement_router
from app.api.routes.store_credit import router as store_credit_router
from app.api.routes.suppliers import router as suppliers_router
from app.api.routes.system_settings import router as system_settings_router
from app.api.routes.user_notification import (
    router as user_notification_router,
)
from app.api.routes.user_preferences import router as user_preferences_router
from app.api.routes.user_review import (
    router as user_review_router,
)
from app.api.routes.user_wishlist import router as user_wishlist_router
from app.api.routes.users_me import router as users_me_router
from app.api.routes.utils import router as utils_router
from app.api.routes.webhooks import router as webhooks_router

api_router = APIRouter()

api_router.include_router(login_router, tags=["login"])
api_router.include_router(password_reset_router)
api_router.include_router(oauth_router)
api_router.include_router(signup_router)
api_router.include_router(partner_router)
api_router.include_router(place_router)
api_router.include_router(payment_router)
api_router.include_router(payment_method_router)
api_router.include_router(payments_router)
api_router.include_router(admin_payments_router)
api_router.include_router(admin_quote_requests_router)
api_router.include_router(admin_orders_router)
api_router.include_router(admin_grouped_departures_router)
api_router.include_router(admin_invoices_router)
api_router.include_router(admin_credit_notes_router)
api_router.include_router(admin_shipping_router)
api_router.include_router(admin_inventory_router)
api_router.include_router(admin_payment_eligibility_router)
api_router.include_router(admin_product_router)
api_router.include_router(admin_price_groups_router)
api_router.include_router(admin_currency_rates_router)
api_router.include_router(admin_tax_rates_router)
api_router.include_router(admin_users_router)
api_router.include_router(admin_carts_router)
api_router.include_router(admin_categories_router)
api_router.include_router(admin_supplier_orders_router)
api_router.include_router(admin_suppliers_router)
api_router.include_router(admin_spec_definitions_router)
api_router.include_router(internal_storage_router)
api_router.include_router(product_catalog_router)
api_router.include_router(product_router)
api_router.include_router(discount_router)
api_router.include_router(cart_router)

# Product related routes
api_router.include_router(category_router)
api_router.include_router(brand_router)
# User groups and security management
api_router.include_router(group_router)
api_router.include_router(group_security_router)

# Order management routes
api_router.include_router(order_status_router)
api_router.include_router(order_router)
api_router.include_router(orders_me_router)
api_router.include_router(invoices_me_router)
api_router.include_router(order_line_router)

api_router.include_router(address_router)
api_router.include_router(user_review_router)
api_router.include_router(user_notification_router)
api_router.include_router(user_wishlist_router)
api_router.include_router(user_preferences_router)
api_router.include_router(users_me_router)
api_router.include_router(group_upgrade_router)
api_router.include_router(system_settings_router)
api_router.include_router(currency_router)
api_router.include_router(content_pages_router)
api_router.include_router(media_router)
api_router.include_router(homepage_router)
api_router.include_router(grouped_departures_router)
api_router.include_router(store_credit_router)
api_router.include_router(stock_alerts_router)
api_router.include_router(utils_router, prefix="/utils")
api_router.include_router(webhooks_router)
api_router.include_router(health_router)

# Shipping routes
api_router.include_router(shipping_router)

# Supplier (distributor) integration routes
api_router.include_router(suppliers_router)

# Icecat product enrichment routes
api_router.include_router(icecat_router, prefix="/icecat", tags=["icecat"])

# Analytics routes
api_router.include_router(analytics_user_router)
api_router.include_router(analytics_sale_router)
api_router.include_router(analytics_product_router)
# Inventory routes
api_router.include_router(inventory_router)
api_router.include_router(stock_movement_router)
