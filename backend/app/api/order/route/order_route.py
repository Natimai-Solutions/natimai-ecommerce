import uuid
from fastapi import APIRouter, HTTPException, status

from app.core.deps import SessionDep, CurrentUser
from app.api.base.routes import BaseController
from app.api.order.crud.order_crud import (
    crud_order,
    crud_order_status,
    OrderCrud,
    OrderStatusCrud,
)
from ..model.order import (
    Order,
    OrderCreate,
    OrderUpdate,
    OrderPublic,
)
from ..model.order_line import (
    OrderLine,
    OrderLineCreate,
    OrderLineUpdate,
    OrderLinePublic,
)
from ..model.order_status import (
    OrderStatus,
    OrderStatusCreate,
    OrderStatusUpdate,
    OrderStatusPublic,
)


# ========== Controllers ==========

class OrderController(
    BaseController[
        Order,
        OrderCreate,
        OrderUpdate,
        OrderCrud,
    ]
):
    pass


class OrderStatusController(
    BaseController[
        OrderStatus,
        OrderStatusCreate,
        OrderStatusUpdate,
        OrderStatusCrud,
    ]
):
    pass


# ========== Routers ==========

router = APIRouter()


# ========== Order Status Routes (Données de référence) ==========

@router.get(
    "/statuses",
    response_model=list[OrderStatusPublic],
    name="order_status:get_all",
)
async def get_all_order_statuses(
    session: SessionDep,
) -> list[OrderStatusPublic]:
    """Récupérer tous les statuts de commande"""
    return await crud_order_status.get_multi(session=session)


@router.get(
    "/statuses/active",
    response_model=list[OrderStatusPublic],
    name="order_status:get_active",
)
async def get_active_order_statuses(
    session: SessionDep,
) -> list[OrderStatusPublic]:
    """Récupérer tous les statuts actifs"""
    return await crud_order_status.get_active_statuses(session=session)


@router.get(
    "/statuses/{status_name}",
    response_model=OrderStatusPublic,
    name="order_status:get_by_name",
)
async def get_order_status_by_name(
    status_name: str,
    session: SessionDep,
) -> OrderStatusPublic:
    """Récupérer un statut par son nom"""
    status = await crud_order_status.get_by_name(session=session, name=status_name)
    if not status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order status '{status_name}' not found"
        )
    return status


# ========== Order Routes Spécialisées ==========

@router.get(
    "/by-status/{status_name}",
    response_model=list[OrderPublic],
    name="order:get_by_status",
)
async def get_orders_by_status(
    status_name: str,
    session: SessionDep,
    limit: int = 100,
) -> list[OrderPublic]:
    """Récupérer les commandes par statut"""
    return await crud_order.get_orders_by_status(
        session=session,
        status_name=status_name,
        limit=limit
    )


@router.get(
    "/user/{user_id}",
    response_model=list[OrderPublic],
    name="order:get_by_user",
)
async def get_orders_by_user(
    user_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
    limit: int = 100,
) -> list[OrderPublic]:
    """Récupérer les commandes d'un utilisateur"""
    # Vérifier que l'utilisateur peut accéder à ces commandes
    # (soit ses propres commandes, soit admin)
    if user_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    return await crud_order.get_orders_by_user(
        session=session,
        user_id=user_id,
        limit=limit
    )


@router.get(
    "/my-orders",
    response_model=list[OrderPublic],
    name="order:get_my_orders",
)
async def get_my_orders(
    session: SessionDep,
    current_user: CurrentUser,
    limit: int = 100,
) -> list[OrderPublic]:
    """Récupérer les commandes de l'utilisateur connecté"""
    return await crud_order.get_orders_by_user(
        session=session,
        user_id=current_user.id,
        limit=limit
    )


@router.patch(
    "/{order_id}/status/{status_id}",
    response_model=OrderPublic,
    name="order:change_status",
)
async def change_order_status(
    order_id: uuid.UUID,
    status_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> OrderPublic:
    """Changer le statut d'une commande"""
    # Vérifier que le statut existe
    status = await crud_order_status.get(session, status_id)
    if not status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order status not found"
        )
    
    result = await crud_order.change_order_status(
        session=session,
        order_id=order_id,
        status_id=status_id,
        user=current_user
    )
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    
    return result


@router.patch(
    "/{order_id}/status-by-name/{status_name}",
    response_model=OrderPublic,
    name="order:change_status_by_name",
)
async def change_order_status_by_name(
    order_id: uuid.UUID,
    status_name: str,
    session: SessionDep,
    current_user: CurrentUser,
) -> OrderPublic:
    """Changer le statut d'une commande par nom de statut"""
    try:
        result = await crud_order.change_order_status_by_name(
            session=session,
            order_id=order_id,
            status_name=status_name,
            user=current_user
        )
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found"
            )
        
        return result
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# ========== Order Lines Routes ==========

@router.post(
    "/{order_id}/lines",
    response_model=OrderLinePublic,
    name="order_line:create",
)
async def add_order_line(
    order_id: uuid.UUID,
    line_data: OrderLineCreate,
    session: SessionDep,
    current_user: CurrentUser,
) -> OrderLinePublic:
    """Ajouter une ligne à une commande"""
    # Vérifier que la commande existe
    order = await crud_order.get(session, order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    
    return await crud_order.add_order_line(
        session=session,
        order_id=order_id,
        line_data=line_data,
        user=current_user
    )


@router.get(
    "/{order_id}/lines",
    response_model=list[OrderLinePublic],
    name="order_line:get_all",
)
async def get_order_lines(
    order_id: uuid.UUID,
    session: SessionDep,
) -> list[OrderLinePublic]:
    """Récupérer toutes les lignes d'une commande"""
    # Vérifier que la commande existe
    order = await crud_order.get(session, order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    
    return await crud_order.get_order_lines(session=session, order_id=order_id)


@router.patch(
    "/lines/{line_id}",
    response_model=OrderLinePublic,
    name="order_line:update",
)
async def update_order_line(
    line_id: uuid.UUID,
    line_data: OrderLineUpdate,
    session: SessionDep,
    current_user: CurrentUser,
) -> OrderLinePublic:
    """Modifier une ligne de commande"""
    result = await crud_order.update_order_line(
        session=session,
        line_id=line_id,
        line_data=line_data,
        user=current_user
    )
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order line not found"
        )
    
    return result


@router.delete(
    "/lines/{line_id}",
    name="order_line:delete",
)
async def remove_order_line(
    line_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> dict[str, str]:
    """Supprimer une ligne de commande"""
    success = await crud_order.remove_order_line(
        session=session,
        line_id=line_id,
        user=current_user
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order line not found"
        )
    
    return {"message": "Order line deleted successfully"}


# ========== Order Analytics Routes ==========

@router.get(
    "/{order_id}/total-quantity",
    response_model=dict[str, int],
    name="order:get_total_quantity",
)
async def get_order_total_quantity(
    order_id: uuid.UUID,
    session: SessionDep,
) -> dict[str, int]:
    """Récupérer la quantité totale d'une commande"""
    # Vérifier que la commande existe
    order = await crud_order.get(session, order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    
    total_quantity = await crud_order.get_order_total_quantity(
        session=session,
        order_id=order_id
    )
    
    return {"total_quantity": total_quantity}


@router.get(
    "/{order_id}/line-count",
    response_model=dict[str, int],
    name="order:get_line_count",
)
async def get_order_line_count(
    order_id: uuid.UUID,
    session: SessionDep,
) -> dict[str, int]:
    """Récupérer le nombre de lignes d'une commande"""
    # Vérifier que la commande existe
    order = await crud_order.get(session, order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    
    line_count = await crud_order.get_order_line_count(
        session=session,
        order_id=order_id
    )
    
    return {"line_count": line_count}


@router.get(
    "/with-details",
    response_model=list[OrderPublic],
    name="order:get_with_details",
)
async def get_orders_with_details(
    session: SessionDep,
    skip: int = 0,
    limit: int = 100,
) -> list[OrderPublic]:
    """Récupérer les commandes avec leurs détails"""
    return await crud_order.get_orders_with_details(
        session=session,
        skip=skip,
        limit=limit
    )


# ========== Configuration des Controllers ==========

# Controller principal pour Order avec routes CRUD complètes
order_controller = OrderController(
    model=Order,
    schema_create=OrderCreate,
    schema_update=OrderUpdate,
    crud=crud_order,
    router=router,
)

# Controller pour OrderStatus (admin uniquement)
order_status_controller = OrderStatusController(
    model=OrderStatus,
    schema_create=OrderStatusCreate,
    schema_update=OrderStatusUpdate,
    crud=crud_order_status,
    router=router,
    prefix="/admin/order-statuses",  # Routes admin séparées
)

# Récupérer le router avec toutes les routes
router = order_controller.get_routes()
