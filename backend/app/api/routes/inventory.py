from app.api.base_router import BaseRouter
from app.features.inventory.crud import InventoryCrud, crud_inventory
from app.features.inventory.models import (
    InventoriesPublic,
    Inventory,
    InventoryCreate,
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
    """Represents inventory router."""

    pass


class Auth:
    """Represents auth."""

    read = True  # Admin only - gestion stock
    create = True  # Admin only
    update = True  # Admin only
    delete = True  # Admin only
    read_superuser = True
    create_superuser = True
    update_superuser = True
    delete_superuser = True


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
