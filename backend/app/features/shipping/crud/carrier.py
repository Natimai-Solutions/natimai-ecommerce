"""CRUD for shipping carriers."""

# mypy: disable-error-code="arg-type,attr-defined"

from sqlmodel import col

from app.features.base.crud import CrudBase
from app.features.shipping.models.carrier import (
    Carrier,
    CarrierCreate,
    CarrierUpdate,
)


class CarrierCrud(CrudBase[Carrier, CarrierCreate, CarrierUpdate]):
    """Represents carrier crud."""


crud_carrier = CarrierCrud(
    model=Carrier,
    schema_create=CarrierCreate,
    schema_update=CarrierUpdate,
    default_filter=col(Carrier.is_active).is_(True),
    order_by=col(Carrier.name).asc(),
)
