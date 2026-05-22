import uuid
from collections.abc import Callable
from typing import Any

from fastapi import Depends

from app.api.base_router import BaseRouter
from app.api.deps import CurrentUser, SessionDep, get_current_user_optional
from app.core.errors import AppError
from app.features.base.crud import RecordNotFoundError
from app.features.order.crud.order_crud import OrderCrud, crud_order
from app.features.order.crud.order_status_crud import crud_order_status
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

    def generate_read_endpoint(self) -> Callable[..., Any]:
        """Generate read endpoint with order-specific error codes."""

        async def read(
            session: SessionDep,
            id: uuid.UUID,
            current_user: CurrentUser | None = Depends(get_current_user_optional),
        ) -> OrderPublic:
            """Execute read."""
            await self._check_auth(session, "read", current_user)
            try:
                record = await self.crud.read(session, id=id, user=current_user)
            except RecordNotFoundError as exc:
                raise AppError(
                    code="order.not_found",
                    status_code=404,
                    message=f"Order '{id}' not found",
                    details={"order_id": str(id)},
                ) from exc

            if (
                current_user is not None
                and not current_user.is_superuser
                and record.user_id != current_user.id
            ):
                raise AppError(
                    code="order.not_owned",
                    status_code=403,
                    message="You cannot access this order",
                    details={"order_id": str(id)},
                )

            return OrderPublic.model_validate(record)

        read.__name__ = f"get_one_{self.name}"
        return read

    def generate_update_endpoint(self) -> Callable[..., Any]:
        """Generate update endpoint with order-specific error codes."""

        async def update(
            session: SessionDep,
            id: uuid.UUID,
            data: OrderUpdate,
            current_user: CurrentUser | None = Depends(get_current_user_optional),
        ) -> OrderPublic:
            """Execute update."""
            await self._check_auth(session, "update", current_user)
            try:
                updated = await self.crud.update(
                    session,
                    id=id,
                    data=data,
                    user=current_user,
                )
            except RecordNotFoundError as exc:
                raise AppError(
                    code="order.not_found",
                    status_code=404,
                    message=f"Order '{id}' not found",
                    details={"order_id": str(id)},
                ) from exc
            return OrderPublic.model_validate(updated)

        update.__name__ = f"update_{self.name}"
        return update

    def generate_delete_endpoint(self) -> Callable[..., Any]:
        """Generate delete endpoint with order-specific error codes."""

        async def delete(
            session: SessionDep,
            id: uuid.UUID,
            current_user: CurrentUser | None = Depends(get_current_user_optional),
        ) -> dict[str, str]:
            """Execute delete."""
            await self._check_auth(session, "delete", current_user)
            try:
                await self.crud.delete(session, id=id, user=current_user)
            except RecordNotFoundError as exc:
                raise AppError(
                    code="order.not_found",
                    status_code=404,
                    message=f"Order '{id}' not found",
                    details={"order_id": str(id)},
                ) from exc
            return {"message": "Deleted successfully"}

        delete.__name__ = f"delete_{self.name}"
        return delete


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
        raise AppError(
            code="order.admin_required",
            status_code=403,
            message="Admin privileges required to access orders by status",
            details={"resource": "order.status"},
        )

    try:
        await crud_order_status.read(
            session=session,
            id=order_status_id,
            user=current_user,
        )
    except RecordNotFoundError as exc:
        raise AppError(
            code="order.status.not_found",
            status_code=404,
            message=f"Order status '{order_status_id}' not found",
            details={"status_name": str(order_status_id)},
        ) from exc

    orders = await crud_order.get_by_status(
        session=session, order_status_id=order_status_id, skip=skip, limit=limit
    )
    return [OrderPublic.model_validate(order) for order in orders]
