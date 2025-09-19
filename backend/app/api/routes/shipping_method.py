from backend.app.api.deps import SessionDep
from backend.app.api.router_generator import BaseController
from fastapi import APIRouter

from app.api.shipping.crud.shipping_method_crud import (
    ShippingMethodCrud,
    crud_shipping_method,
)

from ..model.shipping_method import (
    ShippingMethod,
    ShippingMethodCreate,
    ShippingMethodPublic,
    ShippingMethodUpdate,
)


class ShippingMethodController(
    BaseController[
        ShippingMethod,
        ShippingMethodCreate,
        ShippingMethodUpdate,
        ShippingMethodCrud,
    ]
):
    pass


router = APIRouter()


@router.get(
    "/shipping_methods",
    response_model=list[ShippingMethodPublic],
    name="shipping_method:public",
)
async def get_public_shipping_methods(
    session: SessionDep,
    limit: int = 100,
) -> list[ShippingMethodPublic]:
    return await crud_shipping_method.get_random_shipping_methods(
        session=session,
        limit=limit,
    )


controller = ShippingMethodController(
    model=ShippingMethod,
    schema_create=ShippingMethodCreate,
    schema_update=ShippingMethodUpdate,
    crud=crud_shipping_method,
    router=router,
)

router = controller.get_routes()
