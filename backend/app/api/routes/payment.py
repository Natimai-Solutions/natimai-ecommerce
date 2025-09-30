from app.api.base_router import BaseRouter
from app.api.deps import SessionDep
from app.features.payment.crud.payment import (
    PaymentCrud,
    crud_payment,
)
from app.features.payment.models.payment import (
    Payment,
    PaymentCreate,
    PaymentPublic,
    PaymentsPublic,
    PaymentUpdate,
)


class PaymentRouter(
    BaseRouter[
        Payment,
        PaymentCreate,
        PaymentUpdate,
        PaymentPublic,
        PaymentsPublic,
        PaymentCrud,
    ]
):
    pass


class Auth:
    pass


router = PaymentRouter(
    name="payment",
    tags=["payment"],
    crud=crud_payment,
    schema_public=PaymentPublic,
    schema_publics=PaymentsPublic,
    schema_create=PaymentCreate,
    schema_update=PaymentUpdate,
    auth=Auth(),
    auto=True,
)