from fastapi import APIRouter

from app.core.deps import SessionDep
from backend.app.api.routes.base_routes import BaseController
from app.api.payment.crud.payment_method_crud import (
    crud_payment_method,
    PaymentMethodCrud,
)
from ..models.payment_method import (
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


@router.get(
    "/payment_methods",
    response_model=list[PaymentMethodPublic],
    name="payment_method:public",
)
async def get_public_payment_methods(
    session: SessionDep,
    limit: int = 100,
) -> list[PaymentMethodPublic]:
    return await crud_payment_method.get_random_payment_methods(
        session=session,
        limit=limit,
    )


controller = PaymentMethodController(
    model=PaymentMethod,
    schema_create=PaymentMethodCreate,
    schema_update=PaymentMethodUpdate,
    crud=crud_payment_method,
    router=router,
)

router = controller.get_routes()
