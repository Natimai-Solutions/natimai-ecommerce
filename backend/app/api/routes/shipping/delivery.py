from app.api.base_router import BaseRouter
from app.features.shipping.crud import (
    crud_delivery_task,
    crud_package,
)
from app.features.shipping.models.delivery_task import (
    DeliveryTask,
    DeliveryTaskCreate,
    DeliveryTaskPublic,
    DeliveryTasksPublic,
    DeliveryTaskUpdate,
    Package,
    PackageCreate,
    PackagePublic,
    PackagesPublic,
    PackageUpdate,
)


class DeliveryTaskRouter(
    BaseRouter[
        DeliveryTask,
        DeliveryTaskCreate,
        DeliveryTaskUpdate,
        DeliveryTaskPublic,
        DeliveryTasksPublic,
        type(crud_delivery_task),
    ]
):
    pass


class PackageRouter(
    BaseRouter[
        Package,
        PackageCreate,
        PackageUpdate,
        PackagePublic,
        PackagesPublic,
        type(crud_package),
    ]
):
    pass


class Auth:
    read = True
    create = True
    update = True
    delete = True


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

# Router pour les packages
package_router = PackageRouter(
    name="shipping_package",
    tags=["shipping", "package"],
    crud=crud_package,
    schema_public=PackagePublic,
    schema_publics=PackagesPublic,
    schema_create=PackageCreate,
    schema_update=PackageUpdate,
    auth=Auth(),
    auto=True,
)