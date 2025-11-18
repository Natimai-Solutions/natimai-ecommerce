from app.features.analytic.crud.analytic_product import (
    AnalyticsProductCrud,
    crud_analytics_product,
)
from app.features.analytic.crud.analytic_sale import (
    AnalyticsSaleCrud,
    crud_analytics_sale,
)
from app.features.analytic.crud.analytic_user import (
    AnalyticsUserCrud,
    crud_analytics_user,
)

__all__ = [
    "AnalyticsUserCrud",
    "crud_analytics_user",
    "AnalyticsSaleCrud",
    "crud_analytics_sale",
    "AnalyticsProductCrud",
    "crud_analytics_product",
]
