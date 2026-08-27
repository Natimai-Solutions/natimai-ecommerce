from typing import Any

from app.api.base_router import BaseRouter
from app.features.shipping.crud import (
    crud_delivery_task,
)
from app.features.shipping.models.delivery_task import (
    DeliveryTask,
    DeliveryTaskCreate,
    DeliveryTaskPublic,
    DeliveryTasksPublic,
    DeliveryTaskUpdate,
)


class DeliveryTaskRouter(
    BaseRouter[
        DeliveryTask,
        DeliveryTaskCreate,
        DeliveryTaskUpdate,
        DeliveryTaskPublic,
        DeliveryTasksPublic,
        Any,
    ]
):
    """Represents delivery task router."""

    pass


class Auth:
    """Delivery operations data: superuser-only end to end."""

    read = True
    create = True
    update = True
    delete = True
    read_superuser = True
    create_superuser = True
    update_superuser = True
    delete_superuser = True


# Router pour les tâches de livraison
delivery_task_router = DeliveryTaskRouter(
    name="delivery_task",
    tags=["shipping"],
    crud=crud_delivery_task,
    schema_public=DeliveryTaskPublic,
    schema_publics=DeliveryTasksPublic,
    schema_create=DeliveryTaskCreate,
    schema_update=DeliveryTaskUpdate,
    auth=Auth(),
    auto=True,
)
