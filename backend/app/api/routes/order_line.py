import uuid

from app.api.base_router import BaseRouter
from app.api.deps import CurrentUser, SessionDep
from app.core.errors import AppError
from app.features.base.crud import RecordNotFoundError
from app.features.order.crud.order_crud import crud_order
from app.features.order.crud.order_line_crud import OrderLineCrud, crud_order_line
from app.features.order.models.order_line import (
    OrderLine,
    OrderLineCreate,
    OrderLinePublic,
    OrderLinesPublic,
    OrderLineUpdate,
)


class OrderLineRouter(
    BaseRouter[
        OrderLine,
        OrderLineCreate,
        OrderLineUpdate,
        OrderLinePublic,
        OrderLinesPublic,
        OrderLineCrud,
    ]
):
    """Represents order line router."""

    pass


class Auth:
    """Superuser-only: order lines belong to other customers' orders and the
    generic CRUD has no ownership check. Customers read their lines through
    /orders/me; /order/{order_id} below checks ownership explicitly."""

    read = True
    create = True
    update = True
    delete = True
    read_superuser = True
    create_superuser = True
    update_superuser = True
    delete_superuser = True


router = OrderLineRouter(
    name="order-line",
    tags=["order-line"],
    crud=crud_order_line,
    schema_public=OrderLinePublic,
    schema_publics=OrderLinesPublic,
    schema_create=OrderLineCreate,
    schema_update=OrderLineUpdate,
    auth=Auth(),
    auto=True,
)


@router.get("/order/{order_id}", response_model=list[OrderLinePublic])
async def get_order_lines(
    session: SessionDep,
    current_user: CurrentUser,
    order_id: uuid.UUID,
) -> list[OrderLinePublic]:
    """Get the lines of an order (owner or superuser only)."""
    try:
        order = await crud_order.read(session=session, id=order_id)
    except RecordNotFoundError:
        order = None
    if order is None or (
        not current_user.is_superuser and order.user_id != current_user.id
    ):
        # Same 404 for "missing" and "not yours": don't leak order existence.
        raise AppError(
            code="order.not_found",
            status_code=404,
            message=f"Order '{order_id}' not found",
            details={"order_id": str(order_id)},
        )
    lines = await crud_order_line.get_by_order(session=session, order_id=order_id)
    return [OrderLinePublic.model_validate(line) for line in lines]


@router.get("/product/{product_id}", response_model=list[OrderLinePublic])
async def get_product_order_lines(
    session: SessionDep,
    current_user: CurrentUser,
    product_id: uuid.UUID,
    skip: int = 0,
    limit: int = 100,
) -> list[OrderLinePublic]:
    """Get product order lines."""
    if not current_user.is_superuser:
        raise AppError(
            code="order.admin_required",
            status_code=403,
            message="Admin privileges required to access product order lines",
            details={"resource": "order_line.product"},
        )

    lines = await crud_order_line.get_by_product(
        session=session, product_id=product_id, skip=skip, limit=limit
    )
    return [OrderLinePublic.model_validate(line) for line in lines]


@router.get("/order/{order_id}/total", response_model=dict)
async def calculate_order_total(
    session: SessionDep,
    _current_user: CurrentUser,
    order_id: uuid.UUID,
) -> dict[str, object]:
    """Calculate order total."""
    total = await crud_order_line.calculate_order_total(
        session=session, order_id=order_id
    )
    return {"order_id": str(order_id), "total_amount": total}
