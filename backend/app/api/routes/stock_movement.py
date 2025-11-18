from app.api.base_router import BaseRouter
from app.features.inventory.crud import (
    InventoryStockMovementCrud,
    crud_stock_movement,
)
from app.features.inventory.models import (
    InventoryStockMovement,
    InventoryStockMovementCreate,
    InventoryStockMovementPublic,
    InventoryStockMovementsPublic,
    InventoryStockMovementUpdate,
)


class InventoryStockMovementRouter(
    BaseRouter[
        InventoryStockMovement,
        InventoryStockMovementCreate,
        InventoryStockMovementUpdate,
        InventoryStockMovementPublic,
        InventoryStockMovementsPublic,
        InventoryStockMovementCrud,
    ]
):
    pass


class Auth:
    read = True  # Admin only - gestion stock
    create = True  # Admin only
    update = True  # Admin only
    delete = True  # Admin only


router = InventoryStockMovementRouter(
    name="stock-movement",
    tags=["inventory"],
    crud=crud_stock_movement,
    schema_public=InventoryStockMovementPublic,
    schema_publics=InventoryStockMovementsPublic,
    schema_create=InventoryStockMovementCreate,
    schema_update=InventoryStockMovementUpdate,
    auth=Auth(),
    auto=True,
)
