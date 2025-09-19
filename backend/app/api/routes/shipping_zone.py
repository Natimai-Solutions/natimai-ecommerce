from app.api.base_router import BaseRouter
from app.features.shipping.crud.shipping_zone import (
    crud_shipping_zone,
    ShippingZoneCrud,
)
from app.features.shipping.models.shipping_zone import (
    ShippingZone,
    ShippingZoneCreate,
    ShippingZoneUpdate,
    ShippingZonePublic,
    ShippingZonesPublic
)


class ShippingZoneRouter(
    BaseRouter[
        ShippingZone,
        ShippingZoneCreate,
        ShippingZoneUpdate,
        ShippingZonePublic,
        ShippingZonesPublic,
        ShippingZoneCrud,
    ]
):
    pass


class Auth:
    read = False

router = ShippingZoneRouter(
    name="shipping_zone",
    tags=["shipping"],
    crud=crud_shipping_zone,
    schema_public=ShippingZonePublic,
    schema_publics=ShippingZonesPublic,
    schema_create=ShippingZoneCreate,
    schema_update=ShippingZoneUpdate,
    auth=Auth(),
    auto=True
)
