from app.features.analytic.models.analytic_sale import (
    AnalyticsSale,
    AnalyticsSaleCreate,
    AnalyticsSaleUpdate,
)
from app.features.base.crud import CrudBase


class AnalyticsSaleCrud(
    CrudBase[AnalyticsSale, AnalyticsSaleCreate, AnalyticsSaleUpdate]
):
    """CRUD operations for AnalyticsSale"""

    pass


crud_analytics_sale = AnalyticsSaleCrud(
    model=AnalyticsSale,
    schema_create=AnalyticsSaleCreate,
    schema_update=AnalyticsSaleUpdate,
    order_by=AnalyticsSale.created_at,
    outbox_events={
        "create": "create.analytics_sale",
        "update": "update.analytics_sale",
        "delete": "delete.analytics_sale",
    },
)
