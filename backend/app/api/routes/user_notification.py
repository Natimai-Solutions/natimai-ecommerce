from app.api.base_router import BaseRouter
from app.features.user.crud.notification import (
    crud_notification,
    NotificationCrud,
)
from app.features.user.models.notification import (
    Notification,
    NotificationCreate,
    NotificationUpdate,
    NotificationPublic,
    NotificationsPublic
)


class UserNotificationRouter(
    BaseRouter[
        Notification,
        NotificationCreate,
        NotificationUpdate,
        NotificationPublic,
        NotificationsPublic,
        NotificationCrud,
    ]
):
    pass


class Auth:
    read = True
    create = True
    update = True
    delete = True

router = UserNotificationRouter(
    name="user_notification",
    tags=["notifications"],
    crud=crud_notification,
    schema_public=NotificationPublic,
    schema_publics=NotificationsPublic,
    schema_create=NotificationCreate,
    schema_update=NotificationUpdate,
    auth=Auth(),
    auto=True
)