from app.api.base_router import BaseRouter
from app.features.payment.crud.payment_method import (
    PaymentMethodCrud,
    crud_payment_method,
)
from app.features.payment.models.payment_method import (
    PaymentMethod,
    PaymentMethodCreate,
    PaymentMethodPublic,
    PaymentMethodsPublic,
    PaymentMethodUpdate,
)


class PaymentMethodRouter(
    BaseRouter[
        PaymentMethod,
        PaymentMethodCreate,
        PaymentMethodUpdate,
        PaymentMethodPublic,
        PaymentMethodsPublic,
        PaymentMethodCrud,
    ]
):
    pass


class Auth:
    read: bool = False
    create: bool = True
    update: bool = True
    delete: bool = True


router = PaymentMethodRouter(
    name="payment_method",
    tags=["payment"],
    crud=crud_payment_method,
    schema_public=PaymentMethodPublic,
    schema_publics=PaymentMethodsPublic,
    schema_create=PaymentMethodCreate,
    schema_update=PaymentMethodUpdate,
    auth=Auth(),
    auto=True,
)
