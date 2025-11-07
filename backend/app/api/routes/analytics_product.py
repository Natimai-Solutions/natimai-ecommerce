from app.api.base_router import BaseRouter
from app.features.analytic.crud.analytic_product import (
    AnalyticsProductCrud,
    crud_analytics_product,
)
from app.features.analytic.models.analytic_product import (
    AnalyticsProduct,
    AnalyticsProductCreate,
    AnalyticsProductPublic,
    AnalyticsProductsPublic,
    AnalyticsProductUpdate,
)


class AnalyticsProductRouter(
    BaseRouter[
        AnalyticsProduct,
        AnalyticsProductCreate,
        AnalyticsProductUpdate,
        AnalyticsProductPublic,
        AnalyticsProductsPublic,
        AnalyticsProductCrud,
    ]
):
    pass


class Auth:
    read = True  # Admin only - données sensibles
    create = True  # Admin only
    update = True  # Admin only
    delete = True  # Admin only


router = AnalyticsProductRouter(
    name="analytics-product",
    tags=["analytics"],
    crud=crud_analytics_product,
    schema_public=AnalyticsProductPublic,
    schema_publics=AnalyticsProductsPublic,
    schema_create=AnalyticsProductCreate,
    schema_update=AnalyticsProductUpdate,
    auth=Auth(),
    auto=True,
)
