from app.api.base_router import BaseRouter
from app.features.analytic.crud.analytic_sale import (
    AnalyticsSaleCrud,
    crud_analytics_sale,
)
from app.features.analytic.models.analytic_sale import (
    AnalyticsSale,
    AnalyticsSaleCreate,
    AnalyticsSalePublic,
    AnalyticsSalesPublic,
    AnalyticsSaleUpdate,
)


class AnalyticsSaleRouter(
    BaseRouter[
        AnalyticsSale,
        AnalyticsSaleCreate,
        AnalyticsSaleUpdate,
        AnalyticsSalePublic,
        AnalyticsSalesPublic,
        AnalyticsSaleCrud,
    ]
):
    pass


class Auth:
    read = True  # Admin only - données sensibles
    create = True  # Admin only
    update = True  # Admin only
    delete = True  # Admin only


router = AnalyticsSaleRouter(
    name="analytics-sale",
    tags=["analytics"],
    crud=crud_analytics_sale,
    schema_public=AnalyticsSalePublic,
    schema_publics=AnalyticsSalesPublic,
    schema_create=AnalyticsSaleCreate,
    schema_update=AnalyticsSaleUpdate,
    auth=Auth(),
    auto=True,
)
