from app.api.base_router import BaseRouter
from app.features.inventory.crud import InventoryCrud, crud_inventory
from app.features.inventory.models import (
    Inventory,
    InventoryCreate,
    InventoriesPublic,
    InventoryPublic,
    InventoryUpdate,
)


class InventoryRouter(
    BaseRouter[
        Inventory,
        InventoryCreate,
        InventoryUpdate,
        InventoryPublic,
        InventoriesPublic,
        InventoryCrud,
    ]
):
    pass


class Auth:
    read = True  # Admin only - gestion stock
    create = True  # Admin only
    update = True  # Admin only
    delete = True  # Admin only


router = InventoryRouter(
    name="inventory",
    tags=["inventory"],
    crud=crud_inventory,
    schema_public=InventoryPublic,
    schema_publics=InventoriesPublic,
    schema_create=InventoryCreate,
    schema_update=InventoryUpdate,
    auth=Auth(),
    auto=True,
)
