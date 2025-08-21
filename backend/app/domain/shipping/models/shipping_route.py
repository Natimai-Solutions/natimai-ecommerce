import uuid

from sqlmodel import Field, SQLModel

from app.api.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class ShippingRouteBase(SQLModel):
    name: str = Field(description="Route name", max_length=100)
    shipping_zone_id: uuid.UUID = Field(foreign_key="shipping_zone.id")
    shipping_method_id: uuid.UUID = Field(foreign_key="shipping_method.id")


class ShippingRouteCreate(ShippingRouteBase, BaseCreate):
    pass


class ShippingRouteUpdate(BaseUpdate):
    name: str | None = None


class ShippingRoute(ShippingRouteBase, Base, table=True):
    __tablename__ = "shipping_route"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)


class ShippingRoutePublic(ShippingRouteBase, BasePublic):
    id: uuid.UUID


class ShippingRoutesPublic(SQLModel):
    data: list[ShippingRoutePublic] = Field(default_factory=list)
    count: int = Field(default=0)
