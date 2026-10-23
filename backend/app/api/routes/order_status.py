from app.api.base_router import BaseRouter
from app.features.order.crud.order_status_crud import (
    OrderStatusCrud,
    crud_order_status,
)
from app.features.order.models.order_status import (
    OrderStatus,
    OrderStatusCreate,
    OrderStatusesPublic,
    OrderStatusPublic,
    OrderStatusUpdate,
)


class OrderStatusRouter(
    BaseRouter[
        OrderStatus,
        OrderStatusCreate,
        OrderStatusUpdate,
        OrderStatusPublic,
        OrderStatusesPublic,
        OrderStatusCrud,
    ]
):
    """Represents order status router."""

    pass


class Auth:
    """Represents auth."""

    read = False  # Lecture publique des statuts
    create = True  # Création réservée aux admins
    update = True  # Modification réservée aux admins
    delete = True  # Suppression réservée aux admins
    read_superuser = False  # public labels
    create_superuser = True
    update_superuser = True
    delete_superuser = True


router = OrderStatusRouter(
    name="order-status",
    tags=["order-status"],
    crud=crud_order_status,
    schema_public=OrderStatusPublic,
    schema_publics=OrderStatusesPublic,
    schema_create=OrderStatusCreate,
    schema_update=OrderStatusUpdate,
    auth=Auth(),
    auto=True,
)
