import uuid

from app.api.base_router import BaseRouter
from app.api.deps import CurrentUser, SessionDep
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
    pass


class Auth:
    read = True  # Authentification requise pour lire
    create = True  # Authentification requise pour créer
    update = True  # Authentification requise pour modifier
    delete = True  # Authentification requise pour supprimer


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
    """
    Récupérer toutes les lignes d'une commande.
    """
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
    """
    Récupérer les lignes de commande pour un produit (admin uniquement).
    """
    if not current_user.is_superuser:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux administrateurs",
        )

    lines = await crud_order_line.get_by_product(
        session=session, product_id=product_id, skip=skip, limit=limit
    )
    return [OrderLinePublic.model_validate(line) for line in lines]


@router.get("/order/{order_id}/total", response_model=dict)
async def calculate_order_total(
    session: SessionDep,
    current_user: CurrentUser,
    order_id: uuid.UUID,
) -> dict:
    """
    Calculer le total d'une commande à partir de ses lignes.
    """
    total = await crud_order_line.calculate_order_total(
        session=session, order_id=order_id
    )
    return {"order_id": str(order_id), "total_amount": total}
