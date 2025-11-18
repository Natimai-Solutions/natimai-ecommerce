from app.api.base_router import BaseRouter
from app.features.analytic.crud.analytic_user import (
    AnalyticsUserCrud,
    crud_analytics_user,
)
from app.features.analytic.models.analytic_user import (
    AnalyticsUser,
    AnalyticsUserCreate,
    AnalyticsUserPublic,
    AnalyticsUsersPublic,
    AnalyticsUserUpdate,
)


class AnalyticsUserRouter(
    BaseRouter[
        AnalyticsUser,
        AnalyticsUserCreate,
        AnalyticsUserUpdate,
        AnalyticsUserPublic,
        AnalyticsUsersPublic,
        AnalyticsUserCrud,
    ]
):
    pass


class Auth:
    read = True  # Admin only - données sensibles
    create = True  # Admin only
    update = True  # Admin only
    delete = True  # Admin only


router = AnalyticsUserRouter(
    name="analytics-user",
    tags=["analytics"],
    crud=crud_analytics_user,
    schema_public=AnalyticsUserPublic,
    schema_publics=AnalyticsUsersPublic,
    schema_create=AnalyticsUserCreate,
    schema_update=AnalyticsUserUpdate,
    auth=Auth(),
    auto=True,
)
