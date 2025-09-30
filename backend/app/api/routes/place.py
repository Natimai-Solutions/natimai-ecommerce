from app.api.base_router import BaseRouter
from app.features.place.models import (
    Place,
    PlaceCreate,
    PlacePublic,
    PlacesPublic,
    PlaceUpdate,
)
from app.features.place.crud import crud_place


class PlaceRouter(
    BaseRouter[
        Place,
        PlaceCreate,
        PlaceUpdate,
        PlacePublic,
        PlacesPublic,
        type(crud_place),
    ]
):
    pass


class Auth:
    read = True
    create = True
    update = True
    delete = True


router = PlaceRouter(
    name="place",
    tags=["place"],
    crud=crud_place,
    schema_public=PlacePublic,
    schema_publics=PlacesPublic,
    schema_create=PlaceCreate,
    schema_update=PlaceUpdate,
    auth=Auth(),
    auto=True,
)
