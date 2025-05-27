import datetime
import importlib
import logging
import uuid
from hashlib import md5
from typing import Any, Generic, TypeVar

from fastapi import HTTPException, status
from sqlalchemy.dialects import postgresql
from sqlmodel import SQLModel, func, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel.sql.expression import SelectOfScalar

from api.user.model import User

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ModelType = TypeVar("ModelType", bound=SQLModel)
UserType = TypeVar("UserType", bound=User)
CreateSchemaType = TypeVar("CreateSchemaType", bound=SQLModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=SQLModel)


class CrudBase(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    def __init__(
        self,
        *,
        model: type[ModelType],
        schema_create: type[CreateSchemaType],
        schema_update: type[UpdateSchemaType],
        default_filter: Any | None = None,
        order_by: Any | None = None,
        allow_all_user_to_create: bool = False,
        protected_fields: list[str] | None = [],
    ):
        self.model = model
        self.schema_create = schema_create
        self.schema_update = schema_update
        self.default_filter = default_filter
        self.order_by = order_by
        self.allow_all_user_to_create = allow_all_user_to_create
        self.protected_fields = protected_fields

    def get_query_identifier(self, statement: SelectOfScalar[ModelType]) -> str:
        statement = str(
            statement.compile(
                compile_kwargs={"literal_binds": True}, dialect=postgresql.dialect()
            )
        )
        return md5(str(statement).encode()).hexdigest()

    async def count(
        self, session: AsyncSession, statement: SelectOfScalar[ModelType]
    ) -> int:
        count_statement = select(func.count()).select_from(statement.subquery())
        result = await session.exec(count_statement)
        return result.one()

    async def check_user_permission(
        self,
        session: AsyncSession,
        *,
        user: UserType | None = None,
        record: ModelType | None = None,
        data: CreateSchemaType | UpdateSchemaType | None = None,
        permission: str = "read",
    ) -> bool:
        if not user:
            return False
        if user.is_superuser is True:
            return True
        elif (
            record
            and hasattr(record, "created_by_id")
            and user.id == record.created_by_id
        ):
            return True
        elif record and hasattr(record, "user_id") and user.id == record.user_id:
            return True
        elif permission == "create" and self.allow_all_user_to_create:
            return True
        return False
    
    def remove_protected_fields(
        self,
        data: CreateSchemaType | UpdateSchemaType,
    ) -> CreateSchemaType | UpdateSchemaType:
        protected_fields = self.protected_fields + [
            "created_by_id",
            "created_at",
            "modify_by_id",
            "modify_at",
            "is_admin_active",
        ]
        if isinstance(data, self.schema_create) or isinstance(data, self.schema_update):
            for field in protected_fields:
                print(f"Protected field: {field}")
                if hasattr(data, field):
                    delattr(data, field)
        elif isinstance(data, dict):
            for field in protected_fields:
                data.pop(field, None)
        return data

    async def get(
        self,
        session: AsyncSession,
        *,
        id: uuid.UUID,
        user: UserType | None = None,
    ) -> ModelType | Any:
        record = await session.get(self.model, id)
        if not record:
            raise HTTPException(
                status_code=404,
                detail="L'enregistrement n'existe pas dans la base de données.",
            )
        return record

    async def get_multi_statement(
        self,
        session: AsyncSession,
        *,
        skip: int = 0,
        limit: int = 0,
        ids: list[uuid.UUID] | None = None,
        include_all: bool = False,
        include_all_admin: bool = False,
        filter: Any = None,
        order_by: Any | None = None,
    ) -> SelectOfScalar[ModelType]:
        statement = select(self.model)
        if order_by is None:
            order_by = self.order_by
        if isinstance(order_by, tuple | list):
            statement = statement.order_by(*order_by)
        else:
            statement = statement.order_by(order_by)
        if ids and len(ids):
            statement = statement.where(self.model.id.in_(ids))  # type: ignore
        if include_all is False and self.default_filter is not None:
            statement = statement.where(self.default_filter)
        if filter is not None:
            statement = statement.where(filter)
        return statement

    async def get_multi(
        self,
        session: AsyncSession,
        *,
        statement: SelectOfScalar[ModelType] | None = None,
        skip: int = 0,
        limit: int = 0,
        ids: list[uuid.UUID] | None = None,
        include_all: bool = False,
        filter: Any = None,
        order_by: Any | None = None,
        user: UserType | None = None,
    ) -> dict[str, Any]:
        if statement is None:
            statement = await self.get_multi_statement(
                session,
                skip=skip,
                limit=limit,
                ids=ids,
                include_all=include_all,
                filter=filter,
                order_by=order_by,
            )
        statement_limited = statement
        if skip:
            statement_limited = statement_limited.offset(skip)
        if limit:
            statement_limited = statement_limited.limit(limit)
        logger.debug(f"Requête SQL : {statement_limited}")
        count = await self.count(session, statement)
        result = await session.exec(statement_limited)
        data = result.all()
        return {"data": data, "count": count}

    async def create_draft(
        self, session: AsyncSession, *, data: CreateSchemaType, user: UserType | None
    ) -> ModelType:
        data_dict = data.model_dump(exclude_unset=True)
        current_time = datetime.datetime.now()
        if user and user.id:
            data_dict["created_by_id"] = user.id
        data_dict["created_at"] = current_time
        data_dict["modify_at"] = current_time
        record = self.model(**data_dict)
        session.add(record)
        await session.flush()
        await session.refresh(record)
        return record

    async def before_create(
        self, session: AsyncSession, *, data: CreateSchemaType, user: UserType | None
    ) -> None:
        pass

    async def after_create(
        self,
        session: AsyncSession,
        *,
        record: ModelType | None = None,
        data: CreateSchemaType,
        user: UserType | None,
    ) -> None:
        pass

    async def after_create_commit(
        self,
        session: AsyncSession,
        *,
        record: ModelType | None = None,
        data: CreateSchemaType,
        user: UserType | None,
    ) -> None:
        pass

    async def create(
        self,
        session: AsyncSession,
        *,
        data: CreateSchemaType,
        user: UserType | None,
    ) -> ModelType:
        await self.before_create(session, data=data, user=user)
        if not user or not user.is_superuser:
            # Remove fields from data that the user is not allowed to create
            data = self.remove_protected_fields(data)
        record = await self.create_draft(session, data=data, user=user)
        await self.after_create(session, record=record, data=data, user=user)
        await session.commit()
        await session.refresh(record)
        await self.after_create_commit(session, record=record, data=data, user=user)
        return record

    async def update_draft(
        self,
        session: AsyncSession,
        *,
        id: uuid.UUID,
        data: UpdateSchemaType,
        user: UserType | None = None,
        record: ModelType | None = None,
    ) -> ModelType:
        if not record:
            record = await session.get(self.model, id)
        data_dict = data.model_dump(exclude_unset=True)
        if user and user.id:
            data_dict["modify_by_id"] = user.id
        data_dict["modify_at"] = datetime.datetime.now()
        for key in data_dict.keys():
            if hasattr(record, key):
                setattr(record, key, data_dict[key])
        return record

    async def before_update(
        self,
        session: AsyncSession,
        *,
        data: UpdateSchemaType | None,
        record: ModelType | None = None,
        id: uuid.UUID | None = None,
        user: UserType | None = None,
    ) -> None:
        pass

    async def after_update(
        self,
        session: AsyncSession,
        *,
        data: UpdateSchemaType | None,
        record: ModelType | None = None,
        id: uuid.UUID | None = None,
        user: UserType | None,
    ) -> None:
        pass

    async def after_update_commit(
        self,
        session: AsyncSession,
        *,
        data: UpdateSchemaType | None,
        record: ModelType | None = None,
        id: uuid.UUID | None = None,
        user: UserType | None = None,
    ) -> None:
        pass


    async def update(
        self,
        session: AsyncSession,
        *,
        id: uuid.UUID,
        data: UpdateSchemaType,
        user: UserType | None = None,
        record: ModelType | None = None,
    ) -> ModelType:
        try:
            await self.before_update(
                session, data=data, record=record, id=id, user=user
            )
        except Exception as e:
            logger.error(f"Erreur avant la mise à jour : {e}")
            raise HTTPException(status_code=400, detail=str(e))
        if not user or not user.is_superuser:
            # Remove fields from data that the user is not allowed to update
            data = self.remove_protected_fields(data)
        try:
            record = await self.update_draft(session, id=id, data=data, user=user)
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour : {e}")
            raise HTTPException(status_code=400, detail=str(e))
        try:
            await self.after_update(session, data=data, record=record, id=id, user=user)
        except Exception as e:
            logger.error(f"Erreur après la mise à jour : {e}")
            raise HTTPException(status_code=400, detail=str(e))
        await session.commit()
        await session.refresh(record)
        try:
            await self.after_update_commit(
                session, data=data, record=record, id=id, user=user
            )
        except Exception as e:
            logger.error(f"Erreur après l'enregistrement en base de données: {e}")
        return record

    async def delete_draft(
        self, session: AsyncSession, *, id: uuid.UUID, record: ModelType | None = None
    ) -> None:
        if not record:
            record = await session.get(self.model, id)
        await session.delete(record)

    async def before_delete(
        self, session: AsyncSession, *, id: uuid.UUID, record: ModelType | None = None
    ) -> None:
        pass

    async def after_delete(
        self, session: AsyncSession, *, id: uuid.UUID, record: ModelType | None = None
    ) -> None:
        pass

    async def delete(
        self,
        session: AsyncSession,
        *,
        id: uuid.UUID,
        record: ModelType | None = None,
        user: UserType | None = None,
    ) -> None:
        await self.before_delete(session, id=id, record=record)
        await self.delete_draft(session, id=id, record=record)
        await session.commit()
        await self.after_delete(session, id=id, record=record)

    async def delete_multi(
        self,
        session: AsyncSession,
        *,
        ids: list[uuid.UUID],
        user: UserType | None = None,
    ) -> None:
        for id in ids:
            record = await self.get(session, id=id)
            if not record:
                raise HTTPException(
                    status_code=404,
                    detail="L'un des enregistrement à supprimer n'existe pas dans la base de données.",
                )
            await self.delete_draft(session, id=id, record=record)
        await session.commit()