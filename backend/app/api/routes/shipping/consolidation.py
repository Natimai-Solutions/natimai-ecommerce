from app.api.base_router import BaseRouter
from app.features.shipping.crud import (
    crud_shipping_order_consolidation,
    crud_shipping_order_step_consolidation,
    crud_shipping_route_consolidation,
)
from app.features.shipping.models.consolidation import (
    ShippingOrderConsolidation,
    ShippingOrderConsolidationCreate,
    ShippingOrderConsolidationPublic,
    ShippingOrderConsolidationsPublic,
    ShippingOrderConsolidationUpdate,
    ShippingOrderStepConsolidation,
    ShippingOrderStepConsolidationCreate,
    ShippingOrderStepConsolidationPublic,
    ShippingOrderStepConsolidationsPublic,
    ShippingOrderStepConsolidationUpdate,
    ShippingRouteConsolidation,
    ShippingRouteConsolidationCreate,
    ShippingRouteConsolidationPublic,
    ShippingRouteConsolidationsPublic,
    ShippingRouteConsolidationUpdate,
)


class ShippingRouteConsolidationRouter(
    BaseRouter[
        ShippingRouteConsolidation,
        ShippingRouteConsolidationCreate,
        ShippingRouteConsolidationUpdate,
        ShippingRouteConsolidationPublic,
        ShippingRouteConsolidationsPublic,
        type(crud_shipping_route_consolidation),
    ]
):
    pass


class ShippingOrderConsolidationRouter(
    BaseRouter[
        ShippingOrderConsolidation,
        ShippingOrderConsolidationCreate,
        ShippingOrderConsolidationUpdate,
        ShippingOrderConsolidationPublic,
        ShippingOrderConsolidationsPublic,
        type(crud_shipping_order_consolidation),
    ]
):
    pass


class ShippingOrderStepConsolidationRouter(
    BaseRouter[
        ShippingOrderStepConsolidation,
        ShippingOrderStepConsolidationCreate,
        ShippingOrderStepConsolidationUpdate,
        ShippingOrderStepConsolidationPublic,
        ShippingOrderStepConsolidationsPublic,
        type(crud_shipping_order_step_consolidation),
    ]
):
    pass


class Auth:
    read = True
    create = True
    update = True
    delete = True


# Router pour les consolidations de routes
route_consolidation_router = ShippingRouteConsolidationRouter(
    name="route_consolidation",
    tags=["shipping"],
    crud=crud_shipping_route_consolidation,
    schema_public=ShippingRouteConsolidationPublic,
    schema_publics=ShippingRouteConsolidationsPublic,
    schema_create=ShippingRouteConsolidationCreate,
    schema_update=ShippingRouteConsolidationUpdate,
    auth=Auth(),
    auto=True,
)

# Router pour les consolidations de commandes
order_consolidation_router = ShippingOrderConsolidationRouter(
    name="order_consolidation",
    tags=["shipping"],
    crud=crud_shipping_order_consolidation,
    schema_public=ShippingOrderConsolidationPublic,
    schema_publics=ShippingOrderConsolidationsPublic,
    schema_create=ShippingOrderConsolidationCreate,
    schema_update=ShippingOrderConsolidationUpdate,
    auth=Auth(),
    auto=True,
)

# Router pour les consolidations d'étapes de commandes
order_step_consolidation_router = ShippingOrderStepConsolidationRouter(
    name="order_step_consolidation",
    tags=["shipping"],
    crud=crud_shipping_order_step_consolidation,
    schema_public=ShippingOrderStepConsolidationPublic,
    schema_publics=ShippingOrderStepConsolidationsPublic,
    schema_create=ShippingOrderStepConsolidationCreate,
    schema_update=ShippingOrderStepConsolidationUpdate,
    auth=Auth(),
    auto=True,
)
