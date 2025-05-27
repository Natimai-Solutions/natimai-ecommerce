import uuid
from typing import Any, Generic, TypeVar

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import SQLModel

from app.core.deps import CurrentUser, SessionDep, get_current_user_optional

from .base_crud import CrudBase
from .base_model import Message

ModelType = TypeVar("ModelType", bound=SQLModel)
CreateSchemaType = TypeVar("CreateSchemaType", bound=SQLModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=SQLModel)
PublicSchemaType = TypeVar("PublicSchemaType", bound=SQLModel)
CrudType = TypeVar("CrudType", bound=CrudBase)  # type: ignore



class BaseController(
    Generic[
        ModelType,
        CreateSchemaType,
        UpdateSchemaType,
        PublicSchemaType,
        CrudType,
    ]
):
    def __init__(
        self,
        *,
        model: type[ModelType],
        schema_create: type[CreateSchemaType],
        schema_update: type[UpdateSchemaType],
        schema_public: type[PublicSchemaType],
        crud: CrudType,
        router: APIRouter,
        require_auth: bool = True,
    ):
        self.model = model
        self.schema_create = schema_create
        self.schema_update = schema_update
        self.schema_public = schema_public
        class PublicManySchemaType(
            SQLModel, Generic[PublicSchemaType]
        ):
            items: list[PublicSchemaType]
            count: int
        self.schema_publics = PublicManySchemaType
        self.crud = crud
        self.router = router
        # If require_auth is True, we will check if the user is authenticated for read request.
        # Create, update and delete always need auth.
        self.require_auth = require_auth

    def get_read_items_authorized_users(
        self, session: SessionDep, *, user: CurrentUser | None, query: str | None = None
    ) -> Any | None:
        return None


    def get_routes(self) -> APIRouter:
        @self.router.get("", response_model=self.schema_publics)
        async def read_items(
            session: SessionDep,
            current_user: CurrentUser | None = Depends(get_current_user_optional),
            skip: int = 0,
            limit: int = 100,
            query: str | None = None,
            order_by: str | None = None,
            include_all: bool = False,
        ) -> self.schema_publics:
            """
            Read items.
            """
            # For more flexibility, we authorize both auth and no auth, but if endpoint need auth
            # we check this in the following lines
            if self.require_auth and current_user is None:
                raise HTTPException(
                    status_code=401, detail="L'authentication est requise !"
                )

            return await self.crud.get_multi(
                session,
                skip=skip,
                limit=limit,
                query=query,
                order_by=order_by,
                include_all=include_all,
                user=current_user,
            )

        @self.router.get("/{id}", response_model=self.schema_public)
        async def read_item(
            id: uuid.UUID,
            session: SessionDep,
            current_user: CurrentUser | None = Depends(get_current_user_optional),
        ) -> PublicSchemaType:
            """
            Read one record.
            """
            if self.require_auth and current_user is None:
                raise HTTPException(
                    status_code=403, detail="L'authentication est requise !"
                )
            record = await self.crud.get(session, id=id, user=current_user)
            if not (await self.crud.check_user_permission(
                    session, user=current_user, record=record, permission="read"
            )):
                raise HTTPException(
                    status_code=403,
                    detail="Vous n'avez pas les droits requis pour accéder à cet enregistrement.",
                )
            return record

        @self.router.post("", response_model=self.schema_public)
        async def create_item(
            session: SessionDep,
            *,
            current_user: CurrentUser,
            data_in: self.schema_create,
        ) -> PublicSchemaType:
            """
            Create an item.
            """
            if not (
                await self.crud.check_user_permission(
                    session,
                    user=current_user,
                    data=data_in,
                    permission="create",
                )
            ):
                raise HTTPException(
                    status_code=403,
                    detail="Vous n'avez pas les droits requis pour créer cet enregistrement.",
                )
            return await self.crud.create(session, data=data_in, user=current_user)

        @self.router.patch(
            "/{id}",
            response_model=self.schema_public,
        )
        async def update_item(
            session: SessionDep,
            *,
            current_user: CurrentUser,
            id: uuid.UUID,
            data_in: self.schema_update,
        ) -> PublicSchemaType:
            """
            Update an item.
            """
            record = await self.crud.get(session, id=id)
            if not (
                await self.crud.check_user_permission(
                    session,
                    user=current_user,
                    record=record,
                    data=data_in,
                    permission="update",
                )
            ):
                raise HTTPException(
                    status_code=403,
                    detail="Vous n'avez pas les droits requis pour mettre à jour cet enregistrement.",
                )
            return await self.crud.update(
                session,
                id=id,
                data=data_in,
                record=record,
                user=current_user,
            )

        @self.router.delete("/{id}")
        async def delete_item(
            session: SessionDep,
            current_user: CurrentUser,
            id: uuid.UUID,
        ) -> Message:
            """
            Delete an item.
            """
            record = await self.crud.get(session, id=id)
            if not (
                await self.crud.check_user_permission(
                    session,
                    user=current_user,
                    record=record,
                    permission="delete",
                )
            ):
                raise HTTPException(
                    status_code=403,
                    detail="Vous n'avez pas les droits requis pour supprimer cet enregistrement.",
                )
            await self.crud.delete(session, id=id, user=current_user)
            return Message(id=id, message="L'enregistrement a été supprimé.")

        @self.router.delete("")
        async def delete_items(
            session: SessionDep,
            current_user: CurrentUser,
            ids_in: list[uuid.UUID],
        ) -> Message:
            """
            Delete items.
            """
            for id in ids_in:
                record = await self.crud.get(session, id=id)
                if not (
                    await self.crud.check_user_permission(
                        session, user=current_user, record=record, permission="delete"
                    )
                ):
                    raise HTTPException(
                        status_code=403,
                        detail=f"Vous n'avez pas les droits requis pour supprimer l'un de ces enregistrements ({id}).",
                    )
            await self.crud.delete_multi(session, ids=ids_in, user=current_user)
            return Message(message="Les enregistrements ont été supprimés.")

        for route in self.router.routes:
            model_name = str(self.model.__tablename__)
            if model_name and model_name not in route.name:
                name = route.name.split("_", 1)
                if len(name) > 1:
                    route.name = name[0] + "_" + model_name.capitalize() + "_" + name[1]
                else:
                    route.name = route.name + "_" + model_name.capitalize()
        return self.router
