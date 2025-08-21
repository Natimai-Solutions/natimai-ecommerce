from fastapi import APIRouter

from app.core.deps import SessionDep
from backend.app.api.routes.base_routes import BaseController
from app.api.shipping.crud.shipping_method_crud import (
    crud_shipping_method,
    ShippingMethodCrud,
)
from ..models.shipping_method import (
    ShippingMethod,
    ShippingMethodCreate,
    ShippingMethodUpdate,
    ShippingMethodPublic,
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
