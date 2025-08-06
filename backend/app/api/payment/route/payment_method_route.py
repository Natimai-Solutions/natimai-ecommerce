from fastapi import APIRouter, HTTPException, status

from app.core.deps import SessionDep
from app.api.base.routes import BaseController
from app.api.payment.crud.payment_method_crud import (
    crud_payment_method,
    PaymentMethodCrud,
)
from ..model.payment_method import (
    PaymentMethod,
    PaymentMethodCreate,
    PaymentMethodUpdate,
    PaymentMethodPublic,
)


class PaymentMethodController(
    BaseController[
        PaymentMethod,
        PaymentMethodCreate,
        PaymentMethodUpdate,
        PaymentMethodCrud,
    ]
):
    pass


router = APIRouter()


# ========== Routes spécialisées PaymentMethod ==========

@router.get(
    "/payment-methods",
    response_model=list[PaymentMethodPublic],
    name="payment_method:public",
)
async def get_public_payment_methods(
    session: SessionDep,
    limit: int = 100,
) -> list[PaymentMethodPublic]:
    """Récupérer des méthodes de paiement aléatoires (pour démonstration)"""
    return await crud_payment_method.get_random_payment_methods(
        session=session,
        limit=limit,
    )


@router.get(
    "/payment-methods/active",
    response_model=list[PaymentMethodPublic],
    name="payment_method:active",
)
async def get_active_payment_methods(
    session: SessionDep,
) -> list[PaymentMethodPublic]:
    """Récupérer toutes les méthodes de paiement actives"""
    return await crud_payment_method.get_active_methods(session=session)


@router.get(
    "/payment-methods/checkout",
    response_model=list[PaymentMethodPublic],
    name="payment_method:checkout",
)
async def get_checkout_payment_methods(
    session: SessionDep,
) -> list[PaymentMethodPublic]:
    """Récupérer les méthodes disponibles pour le checkout"""
    return await crud_payment_method.get_enabled_for_checkout(session=session)


@router.get(
    "/payment-methods/{method_name}",
    response_model=PaymentMethodPublic,
    name="payment_method:get_by_name",
)
async def get_payment_method_by_name(
    method_name: str,
    session: SessionDep,
) -> PaymentMethodPublic:
    """Récupérer une méthode de paiement par son nom"""
    method = await crud_payment_method.get_by_name(session=session, name=method_name)
    if not method:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Payment method '{method_name}' not found"
        )
    return method

# ========== Configuration du Controller ==========

controller = PaymentMethodController(
    model=PaymentMethod,
    schema_create=PaymentMethodCreate,
    schema_update=PaymentMethodUpdate,
    crud=crud_payment_method,
    router=router,
)

router = controller.get_routes()
