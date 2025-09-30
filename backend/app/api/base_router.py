import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any, Generic, TypeVar

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
CrudType = TypeVar("CrudType", bound=CrudBase)  # type: ignore


@dataclass
class Routes:
    path: str
    endpoint: Any
    methods: list[str]
    tags: list[str]
    response_model: Any = None  # Optional response model for the route


class Auth:
    read = True
    create = True
    update = True
    delete = True


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
    def __init__(
        self,
        name: str,
        crud: CrudType,
        schema_public: PublicSchemaType | None = None,
        schema_publics: PublicsSchemaType | None = None,
        schema_create: CreateSchemaType | None = None,
        schema_update: UpdateSchemaType | None = None,
        auth: Auth | None = None,
        tags: list[str] | None = None,
        routes_before: list[Routes] | None = None,
        routes_after: list[Routes] | None = None,
        auto: bool = False,
        *args,
        **kwargs,
    ) -> None:
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

        self.schema_create = schema_create
        self.schema_update = schema_update
        self.schema_public = schema_public
        self.schema_publics = schema_publics

        if not kwargs.get("prefix"):
            path = name.lower()
            path = path.replace(" ", "_")
            kwargs["prefix"] = f"/{path}"

        self.tags = tags or [self.name]

        kwargs["tags"] = self.tags

        super().__init__(*args, **kwargs)

        # Stocker les routes personnalisées
        self.routes_before = routes_before or []
        self.routes_after = routes_after or []

        if auto:
            self.generate_endpoints()

    async def _check_auth(
        self, session: SessionDep, permission: str, current_user: CurrentUser | None
    ):
        """Helper method to check authorization for an endpoint."""
        auth_required = getattr(self.auth, permission, True)
        if auth_required and current_user is None:
            raise HTTPException(
                status_code=403, detail=f"Authentication required on {self.name}"
            )

        if current_user and not await self.crud.check_user_permission(
            session, user=current_user, permission=permission
        ):
            raise HTTPException(
                status_code=403, detail=f"Not authorized to {permission} on {self.name}"
            )

    def generate_read_multi_endpoint(self):
        async def read_multi(
            session: SessionDep,
            skip: int = 0,
            limit: int = 1000,
            filter: str | None = None,
            order_by: str | None = None,
            include_archived: bool = False,
            current_user: CurrentUser | None = Depends(get_current_user_optional),
        ) -> PublicsSchemaType:
            await self._check_auth(session, "read", current_user)
            result = await self.crud.read_multi(
                session,
                skip=skip,
                limit=limit,
                filter=filter,
                order_by=order_by,
                include_archived=include_archived,
                user=current_user,
            )
            return result  # Return the complete dict with 'data' and 'count'

        read_multi.__name__ = f"get_multiple_{self.name}s"
        return read_multi

    def generate_read_endpoint(self) -> Callable:
        async def read(
            session: SessionDep,
            id: uuid.UUID,  # Fixed: use UUID instead of int
            current_user: CurrentUser | None = Depends(get_current_user_optional),
        ) -> PublicSchemaType:
            await self._check_auth(session, "read", current_user)
            try:
                record = await self.crud.read(session, id=id, user=current_user)
            except RecordNotFoundError:
                raise HTTPException(status_code=404, detail=f"{self.name} not found")
            return record

        read.__name__ = f"get_one_{self.name}"
        return read

    def generate_create_endpoint(self) -> Callable:
        async def create(
            session: SessionDep,
            data: self.schema_create,  # type: ignore
            current_user: CurrentUser | None = Depends(get_current_user_optional),
        ) -> PublicSchemaType:
            await self._check_auth(session, "create", current_user)
            return await self.crud.create(session, data=data, user=current_user)

        create.__name__ = f"create_{self.name}"
        return create

    def generate_update_endpoint(self) -> Callable:
        async def update(
            session: SessionDep,
            id: uuid.UUID,  # Fixed: use UUID
            data: self.schema_update,  # type: ignore
            current_user: CurrentUser | None = Depends(get_current_user_optional),
        ):
            await self._check_auth(session, "update", current_user)
            return await self.crud.update(session, id=id, data=data, user=current_user)

        update.__name__ = f"update_{self.name}"
        return update

    def generate_delete_endpoint(self) -> Callable:
        async def delete(
            session: SessionDep,
            id: uuid.UUID,  # Fixed: use UUID
            current_user: CurrentUser | None = Depends(get_current_user_optional),
        ):
            await self._check_auth(session, "delete", current_user)
            await self.crud.delete(session, id=id, user=current_user)
            return {"message": "Deleted successfully"}

        delete.__name__ = f"delete_{self.name}"
        return delete

    def generate_endpoints(
        self,
        routes: list[Routes] | None = None,
    ) -> APIRouter:
        default_routes = [
            Routes(
                path="/",
                endpoint=self.generate_read_multi_endpoint(),
                methods=["GET"],
                tags=self.tags,
                response_model=self.schema_publics,
            ),
            Routes(
                path="/{id}",
                endpoint=self.generate_read_endpoint(),
                methods=["GET"],
                tags=self.tags,
                response_model=self.schema_public,
            ),
            Routes(
                path="/",
                endpoint=self.generate_create_endpoint(),
                methods=["POST"],
                tags=self.tags,
                response_model=self.schema_public,
            ),
            Routes(
                path="/{id}",
                endpoint=self.generate_update_endpoint(),
                methods=["PUT"],
                tags=self.tags,
                response_model=self.schema_public,
            ),
            Routes(
                path="/{id}",
                endpoint=self.generate_delete_endpoint(),
                methods=["DELETE"],
                tags=self.tags,
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
