from fastapi import APIRouter

from app.core.deps import SessionDep
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


@router.get(
    "/payments",
    response_model=list[PaymentPublic],
    name="payment:public",
)
async def get_public_payments(
    session: SessionDep,
    limit: int = 100,
) -> list[PaymentPublic]:
    return await crud_payment.get_random_payments(
        session=session,
        limit=limit,
    )


controller = PaymentController(
    model=Payment,
    schema_create=PaymentCreate,
    schema_update=PaymentUpdate,
    crud=crud_payment,
    router=router,
)

router = controller.get_routes()
