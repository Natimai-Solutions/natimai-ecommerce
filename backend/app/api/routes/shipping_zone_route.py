from fastapi import APIRouter

from app.core.deps import SessionDep
from backend.app.api.routes.base_routes import BaseController
from app.api.shipping.crud.shipping_zone_crud import (
    crud_shipping_zone,
    ShippingZoneCrud,
)
from ..models.shipping_zone import (
    ShippingZone,
    ShippingZoneCreate,
    ShippingZoneUpdate,
    ShippingZonePublic,
)


class ShippingZoneController(
    BaseController[
        ShippingZone,
        ShippingZoneCreate,
        ShippingZoneUpdate,
        ShippingZoneCrud,
    ]
):
    pass


router = APIRouter()


@router.get(
    "/shipping_zones",
    response_model=list[ShippingZonePublic],
    name="shipping_zone:public",
)
async def get_public_shipping_zones(
    session: SessionDep,
    limit: int = 100,
) -> list[ShippingZonePublic]:
    return await crud_shipping_zone.get_random_shipping_zones(
        session=session,
        limit=limit,
    )


controller = ShippingZoneController(
    model=ShippingZone,
    schema_create=ShippingZoneCreate,
    schema_update=ShippingZoneUpdate,
    crud=crud_shipping_zone,
    router=router,
)

router = controller.get_routes()
