from backend.app.api.deps import SessionDep
from fastapi import APIRouter

from app.api.routes.base import BaseController
from app.api.shipping.crud.shipping_status_crud import (
    ShippingStatusCrud,
    crud_shipping_status,
)

from ..model.shipping_status import (
    ShippingStatus,
    ShippingStatusCreate,
    ShippingStatusPublic,
    ShippingStatusUpdate,
)


class ShippingStatusController(
    BaseController[
        ShippingStatus,
        ShippingStatusCreate,
        ShippingStatusUpdate,
        ShippingStatusCrud,
    ]
):
    pass


router = APIRouter()


@router.get(
    "/shipping_statuses",
    response_model=list[ShippingStatusPublic],
    name="shipping_status:public",
)
async def get_public_shipping_statuses(
    session: SessionDep,
    limit: int = 100,
) -> list[ShippingStatusPublic]:
    return await crud_shipping_status.get_random_shipping_statuses(
        session=session,
        limit=limit,
    )


controller = ShippingStatusController(
    model=ShippingStatus,
    schema_create=ShippingStatusCreate,
    schema_update=ShippingStatusUpdate,
    crud=crud_shipping_status,
    router=router,
)

router = controller.get_routes()
