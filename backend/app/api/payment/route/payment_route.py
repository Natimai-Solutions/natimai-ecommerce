import uuid
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import SessionDep, get_current_user
from app.api.user.model.user import User
from app.api.base.routes import BaseController
from app.api.payment.crud.payment_crud import (
    crud_payment,
    PaymentCrud,
)
from ..model.payment import (
    Payment,
    PaymentCreate,
    PaymentUpdate,
    PaymentPublic,
)


class PaymentController(
    BaseController[
        Payment,
        PaymentCreate,
        PaymentUpdate,
        PaymentCrud,
    ]
):
    pass


router = APIRouter()


# ========== Routes spécialisées Payment ==========

@router.get(
    "/payments",
    response_model=list[PaymentPublic],
    name="payment:public",
)
async def get_public_payments(
    session: SessionDep,
    limit: int = 100,
) -> list[PaymentPublic]:
    """Récupérer des paiements aléatoires (pour démonstration)"""
    return await crud_payment.get_random_payments(
        session=session,
        limit=limit,
    )


@router.get(
    "/order/{order_id}",
    response_model=list[PaymentPublic],
    name="payment:get_by_order",
)
async def get_payments_by_order(
    order_id: uuid.UUID,
    session: SessionDep,
) -> list[PaymentPublic]:
    """Récupérer tous les paiements d'une commande"""
    return await crud_payment.get_payments_by_order(
        session=session,
        order_id=order_id,
    )


@router.get(
    "/user/{user_id}",
    response_model=list[PaymentPublic],
    name="payment:get_by_user",
)
async def get_payments_by_user(
    user_id: uuid.UUID,
    session: SessionDep,
    current_user: User = Depends(get_current_user),
    limit: int = 100,
) -> list[PaymentPublic]:
    """Récupérer les paiements d'un utilisateur"""
    # Vérifier que l'utilisateur peut accéder à ces paiements
    if user_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    return await crud_payment.get_payments_by_user(
        session=session,
        user_id=user_id,
        limit=limit,
    )


@router.get(
    "/my-payments",
    response_model=list[PaymentPublic],
    name="payment:get_my_payments",
)
async def get_my_payments(
    session: SessionDep,
    current_user: User = Depends(get_current_user),
    limit: int = 100,
) -> list[PaymentPublic]:
    """Récupérer les paiements de l'utilisateur connecté"""
    return await crud_payment.get_payments_by_user(
        session=session,
        user_id=current_user.id,
        limit=limit,
    )


@router.get(
    "/status/{status_id}",
    response_model=list[PaymentPublic],
    name="payment:get_by_status",
)
async def get_payments_by_status(
    status_id: uuid.UUID,
    session: SessionDep,
    limit: int = 100,
) -> list[PaymentPublic]:
    """Récupérer les paiements par statut"""
    return await crud_payment.get_payments_by_status(
        session=session,
        status_id=status_id,
        limit=limit,
    )


@router.get(
    "/order/{order_id}/total",
    response_model=dict[str, float],
    name="payment:get_total_by_order",
)
async def get_total_amount_by_order(
    order_id: uuid.UUID,
    session: SessionDep,
) -> dict[str, float]:
    """Calculer le montant total des paiements pour une commande"""
    total = await crud_payment.get_total_amount_by_order(
        session=session,
        order_id=order_id,
    )
    return {"total_amount": total}

# ========== Configuration du Controller ==========

controller = PaymentController(
    model=Payment,
    schema_create=PaymentCreate,
    schema_update=PaymentUpdate,
    crud=crud_payment,
    router=router,
)

router = controller.get_routes()
