from app.api.base_router import BaseRouter
from app.features.shipping.crud import (
    crud_status_definition,
    crud_status_transition,
)
from app.features.shipping.models.status import (
    StatusDefinition,
    StatusDefinitionCreate,
    StatusDefinitionPublic,
    StatusDefinitionsPublic,
    StatusDefinitionUpdate,
    StatusTransition,
    StatusTransitionCreate,
    StatusTransitionPublic,
    StatusTransitionsPublic,
    StatusTransitionUpdate,
)


class StatusDefinitionRouter(
    BaseRouter[
        StatusDefinition,
        StatusDefinitionCreate,
        StatusDefinitionUpdate,
        StatusDefinitionPublic,
        StatusDefinitionsPublic,
        type(crud_status_definition),
    ]
):
    pass


class StatusTransitionRouter(
    BaseRouter[
        StatusTransition,
        StatusTransitionCreate,
        StatusTransitionUpdate,
        StatusTransitionPublic,
        StatusTransitionsPublic,
        type(crud_status_transition),
    ]
):
    pass


class Auth:
    read = True
    create = True
    update = True
    delete = True


# Router pour les définitions de statuts
status_definition_router = StatusDefinitionRouter(
    name="status_definition",
    tags=["shipping"],
    crud=crud_status_definition,
    schema_public=StatusDefinitionPublic,
    schema_publics=StatusDefinitionsPublic,
    schema_create=StatusDefinitionCreate,
    schema_update=StatusDefinitionUpdate,
    auth=Auth(),
    auto=True,
)

# Router pour les transitions de statuts
status_transition_router = StatusTransitionRouter(
    name="status_transition",
    tags=["shipping"],
    crud=crud_status_transition,
    schema_public=StatusTransitionPublic,
    schema_publics=StatusTransitionsPublic,
    schema_create=StatusTransitionCreate,
    schema_update=StatusTransitionUpdate,
    auth=Auth(),
    auto=True,
)
