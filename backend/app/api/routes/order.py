import uuid

from app.api.base_router import BaseRouter
from app.api.deps import CurrentUser, SessionDep
from app.features.order.crud.order_crud import OrderCrud, crud_order
from app.features.order.models.order import (
    Order,
    OrderCreate,
    OrderPublic,
    OrdersPublic,
    OrderUpdate,
)


class OrderRouter(
    BaseRouter[
        Order,
        OrderCreate,
        OrderUpdate,
        OrderPublic,
        OrdersPublic,
        OrderCrud,
    ]
):
    """Represents order router."""

    pass


class Auth:
    """Represents auth."""

    read = True  # Authentification requise pour lire les commandes
    create = True  # Authentification requise pour créer
    update = True  # Authentification requise pour modifier
    delete = True  # Authentification requise pour supprimer


router = OrderRouter(
    name="order",
    tags=["order"],
    crud=crud_order,
    schema_public=OrderPublic,
    schema_publics=OrdersPublic,
    schema_create=OrderCreate,
    schema_update=OrderUpdate,
    auth=Auth(),
    auto=True,
)


@router.get("/user/{user_id}", response_model=list[OrderPublic])
async def get_user_orders(
    session: SessionDep,
    current_user: CurrentUser,
    user_id: uuid.UUID,
    skip: int = 0,
    limit: int = 100,
) -> list[OrderPublic]:
    """Get user orders."""
    # Vérifier que l'utilisateur accède à ses propres commandes ou est admin
    if current_user.id != user_id and not current_user.is_superuser:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous ne pouvez accéder qu'à vos propres commandes",
        )

    orders = await crud_order.get_by_user(
        session=session, user_id=user_id, skip=skip, limit=limit
    )
    return [OrderPublic.model_validate(order) for order in orders]


@router.get("/status/{order_status_id}", response_model=list[OrderPublic])
async def get_orders_by_status(
    session: SessionDep,
    current_user: CurrentUser,
    order_status_id: uuid.UUID,
    skip: int = 0,
    limit: int = 100,
) -> list[OrderPublic]:
    """Get orders by status."""
    if not current_user.is_superuser:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux administrateurs",
        )

    orders = await crud_order.get_by_status(
        session=session, order_status_id=order_status_id, skip=skip, limit=limit
    )
    return [OrderPublic.model_validate(order) for order in orders]
