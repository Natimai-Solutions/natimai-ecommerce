from app.api.base_router import BaseRouter
from app.features.shipping.crud import (
    crud_tracking_event,
)
from app.features.shipping.models.tracking import (
    TrackingEvent,
    TrackingEventCreate,
    TrackingEventPublic,
    TrackingEventsPublic,
    TrackingEventUpdate,
)


class TrackingEventRouter(
    BaseRouter[
        TrackingEvent,
        TrackingEventCreate,
        TrackingEventUpdate,
        TrackingEventPublic,
        TrackingEventsPublic,
        type(crud_tracking_event),
    ]
):
    pass


class Auth:
    read = True
    create = True
    update = True
    delete = True


# Router pour les événements de tracking
tracking_event_router = TrackingEventRouter(
    name="tracking_event",
    tags=["shipping"],
    crud=crud_tracking_event,
    schema_public=TrackingEventPublic,
    schema_publics=TrackingEventsPublic,
    schema_create=TrackingEventCreate,
    schema_update=TrackingEventUpdate,
    auth=Auth(),
    auto=True,
)
