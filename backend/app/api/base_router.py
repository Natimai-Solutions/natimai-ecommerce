import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any, Generic, Protocol, TypeVar, cast

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import SQLModel

from app.api.deps import CurrentUser, SessionDep, get_current_user_optional
from app.features.base.crud import CrudBase, RecordNotFoundError
from app.features.base.models import Message

ModelType = TypeVar("ModelType", bound=SQLModel)
CreateSchemaType = TypeVar("CreateSchemaType", bound=SQLModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=SQLModel)
PublicSchemaType = TypeVar("PublicSchemaType", bound=SQLModel)
PublicsSchemaType = TypeVar("PublicsSchemaType", bound=SQLModel)
CrudType = TypeVar("CrudType", bound=CrudBase[Any, Any, Any])


@dataclass
class Routes:
    """Represents routes."""

    path: str
    endpoint: Any
    methods: list[str]
    tags: list[str]
    response_model: Any = None  # Optional response model for the route


class Auth:
    """Represents auth."""

    read: bool = True
    create: bool = True
    update: bool = True
    delete: bool = True
    read_superuser: bool = False
    create_superuser: bool = False
    update_superuser: bool = False
    delete_superuser: bool = False


class AuthConfig(Protocol):
    """Represents auth config."""

    read: bool
    create: bool
    update: bool
    delete: bool


class BaseRouter(
    Generic[
        ModelType,
        CreateSchemaType,
        UpdateSchemaType,
        PublicSchemaType,
        PublicsSchemaType,
        CrudType,
    ],
    APIRouter,
):
    """Represents base router."""

    def __init__(
        self,
        name: str,
        crud: CrudType,
        schema_public: type[PublicSchemaType] | None = None,
        schema_publics: type[PublicsSchemaType] | None = None,
        schema_create: type[CreateSchemaType] | None = None,
        schema_update: type[UpdateSchemaType] | None = None,
        auth: type[AuthConfig] | AuthConfig | None = None,
        tags: list[str] | None = None,
        routes_before: list[Routes] | None = None,
        routes_after: list[Routes] | None = None,
        auto: bool = False,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Initialize the base router instance."""
        self.name = "".join(
            [
                c.upper() if (i == 0 or name[i - 1] == "_" or name[i - 1] == " ") else c
                for i, c in enumerate(name)
            ]
        )
        self.crud = crud

        self.auth = auth() if isinstance(auth, type) else auth or Auth()

        if not hasattr(self.auth, "read"):
            self.auth.read = True
        if not hasattr(self.auth, "create"):
            self.auth.create = True
        if not hasattr(self.auth, "update"):
            self.auth.update = True
        if not hasattr(self.auth, "delete"):
            self.auth.delete = True
        if not hasattr(self.auth, "read_superuser"):
            self.auth.read_superuser = False
        if not hasattr(self.auth, "create_superuser"):
            self.auth.create_superuser = False
        if not hasattr(self.auth, "update_superuser"):
            self.auth.update_superuser = False
        if not hasattr(self.auth, "delete_superuser"):
            self.auth.delete_superuser = False

        self.schema_create = schema_create
        self.schema_update = schema_update
        self.schema_public = schema_public
        self.schema_publics = schema_publics

        if not kwargs.get("prefix"):
            path = name.lower()
            path = path.replace(" ", "_")
            kwargs["prefix"] = f"/{path}"

        self.route_tags = tags or [self.name]

        kwargs["tags"] = self.route_tags

        super().__init__(*args, **kwargs)

        # Stocker les routes personnalisées
        self.routes_before = routes_before or []
        self.routes_after = routes_after or []

        if auto:
            self.generate_endpoints()

    async def _check_auth(
        self, session: SessionDep, permission: str, current_user: CurrentUser | None
    ) -> None:
        """Helper method to check authorization for an endpoint."""
        auth_required = getattr(self.auth, permission, True)
        superuser_required = getattr(self.auth, f"{permission}_superuser", False)

        if auth_required and current_user is None:
            raise HTTPException(
                status_code=403, detail=f"Authentication required on {self.name}"
            )

        if superuser_required and (
            current_user is None or not current_user.is_superuser
        ):
            raise HTTPException(
                status_code=403,
                detail=f"Superuser privileges required to {permission} on {self.name}",
            )

        if current_user and not await self.crud.check_user_permission(
            session, user=current_user, permission=permission
        ):
            raise HTTPException(
                status_code=403, detail=f"Not authorized to {permission} on {self.name}"
            )

    def generate_read_multi_endpoint(self) -> Callable[..., Any]:
        """Generate read multi endpoint."""

        async def read_multi(
            session: SessionDep,
            skip: int = 0,
            limit: int = 1000,
            filter: str | None = None,
            order_by: str | None = None,
            include_archived: bool = False,
            current_user: CurrentUser | None = Depends(get_current_user_optional),
        ) -> Any:
            """Read multi."""
            await self._check_auth(session, "read", current_user)
            if filter is not None:
                raise HTTPException(
                    status_code=400,
                    detail="Raw string filters are not supported on this endpoint",
                )
            result = await self.crud.read_multi(
                session,
                skip=skip,
                limit=limit,
                filter=None,
                order_by=order_by,
                include_archived=include_archived,
                user=current_user,
            )
            return result  # Return the complete dict with 'data' and 'count'

        read_multi.__name__ = f"get_multiple_{self.name}s"
        return read_multi

    def generate_read_endpoint(self) -> Callable[..., Any]:
        """Generate read endpoint."""

        async def read(
            session: SessionDep,
            id: uuid.UUID,  # Fixed: use UUID instead of int
            current_user: CurrentUser | None = Depends(get_current_user_optional),
        ) -> PublicSchemaType:
            """Execute read."""
            await self._check_auth(session, "read", current_user)
            try:
                record = await self.crud.read(session, id=id, user=current_user)
            except RecordNotFoundError:
                raise HTTPException(status_code=404, detail=f"{self.name} not found")
            return cast(PublicSchemaType, record)

        read.__name__ = f"get_one_{self.name}"
        return read

    def generate_create_endpoint(self) -> Callable[..., Any]:
        """Generate create endpoint."""

        async def create(
            session: SessionDep,
            data: CreateSchemaType,
            current_user: CurrentUser | None = Depends(get_current_user_optional),
        ) -> PublicSchemaType:
            """Execute create."""
            await self._check_auth(session, "create", current_user)
            created = await self.crud.create(session, data=data, user=current_user)
            return cast(PublicSchemaType, created)

        create.__name__ = f"create_{self.name}"
        return create

    def generate_update_endpoint(self) -> Callable[..., Any]:
        """Generate update endpoint."""

        async def update(
            session: SessionDep,
            id: uuid.UUID,  # Fixed: use UUID
            data: UpdateSchemaType,
            current_user: CurrentUser | None = Depends(get_current_user_optional),
        ) -> PublicSchemaType:
            """Execute update."""
            await self._check_auth(session, "update", current_user)
            updated = await self.crud.update(
                session, id=id, data=data, user=current_user
            )
            return cast(PublicSchemaType, updated)

        update.__name__ = f"update_{self.name}"
        return update

    def generate_delete_endpoint(self) -> Callable[..., Any]:
        """Generate delete endpoint."""

        async def delete(
            session: SessionDep,
            id: uuid.UUID,  # Fixed: use UUID
            current_user: CurrentUser | None = Depends(get_current_user_optional),
        ) -> Message:
            """Execute delete."""
            await self._check_auth(session, "delete", current_user)
            await self.crud.delete(session, id=id, user=current_user)
            return Message(message="Deleted successfully")

        delete.__name__ = f"delete_{self.name}"
        return delete

    def generate_endpoints(
        self,
        routes: list[Routes] | None = None,
    ) -> APIRouter:
        """Generate endpoints."""
        default_routes = [
            Routes(
                path="/",
                endpoint=self.generate_read_multi_endpoint(),
                methods=["GET"],
                tags=self.route_tags,
                response_model=self.schema_publics,
            ),
            Routes(
                path="/{id}",
                endpoint=self.generate_read_endpoint(),
                methods=["GET"],
                tags=self.route_tags,
                response_model=self.schema_public,
            ),
            Routes(
                path="/",
                endpoint=self.generate_create_endpoint(),
                methods=["POST"],
                tags=self.route_tags,
                response_model=self.schema_public,
            ),
            Routes(
                path="/{id}",
                endpoint=self.generate_update_endpoint(),
                methods=["PUT"],
                tags=self.route_tags,
                response_model=self.schema_public,
            ),
            Routes(
                path="/{id}",
                endpoint=self.generate_delete_endpoint(),
                methods=["DELETE"],
                tags=self.route_tags,
                response_model=Message,
            ),
        ]

        if routes is None or len(routes) == 0:
            routes = default_routes

        if self.routes_before is not None and len(self.routes_before) > 0:
            routes = self.routes_before + routes

        if self.routes_after is not None and len(self.routes_after) > 0:
            routes.extend(self.routes_after)

        for route in routes:
            self.add_api_route(**asdict(route))

        return self
