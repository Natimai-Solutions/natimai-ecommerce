import datetime
import importlib
import logging
import uuid
from hashlib import md5
from typing import Any, Generic, TypeVar

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

class RecordNotFoundError(Exception):
    """Levée quand un enregistrement n'est pas trouvé."""
    pass

class PermissionDeniedError(Exception):
    """Levée quand un utilisateur n'a pas les permissions."""
    pass


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
        self.event_handlers = {}

    def register_event_handler(self, event_name: str, handler_func: callable):
        """Register a handler for a specific event"""
        if event_name not in self.event_handlers:
            self.event_handlers[event_name] = []
        self.event_handlers[event_name].append(handler_func)
        return self  # Pour permettre le chaînage

    async def trigger_event(self, event_name: str, **context):
        """Trigger all handlers registered for a specific event"""
        if event_name not in self.event_handlers:
            logger.debug(f"The event {event_name} has no handlers registered.")
            return
        
        logger.debug(f"Triggering event {event_name} with {len(self.event_handlers[event_name])} handlers")
        for handler in self.event_handlers[event_name]:
            try:
                result = handler(**context)
                # Gère à la fois les fonctions synchrones et asynchrones
                if hasattr(result, '__await__'):
                    await result
            except Exception as e:
                logger.error(f"Error in event handler for {event_name}: {e}")
                # Ne pas propager l'erreur pour ne pas bloquer le flux principal

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

    async def get(
        self,
        session: AsyncSession,
        *,
        id: uuid.UUID,
        user: UserType | None = None,
    ) -> ModelType | Any:
        record = await session.get(self.model, id)
        if not record:
            logger.error(f"The record with id {id} does not exist.")
            raise RecordNotFoundError("The record doesn't exists.")
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
        try:
            count = await self.count(session, statement)
        except Exception as e:
            logger.error(f"Error while counting records: {e}")
            raise Exception("An error occurred while counting the records.")
        try:
            result = await session.exec(statement_limited)
            data = result.all()
        except Exception as e:
            logger.error(f"Error while executing the query: {e}")
            raise Exception("An error occurred while executing the query.")
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
        try:
            record = await self.create_draft(session, data=data, user=user)
        except Exception as e:
            logger.error(f"Error while creating the record: {e}")
            raise Exception("An error occurred while creating the record.")
        try:
            await self.after_create(session, record=record, data=data, user=user)
        except Exception as e:
            logger.error(f"Error after creating the record: {e}")
            raise Exception("An error occurred after creating the record.")
        try:
            await session.commit()
        except Exception as e:
            logger.error(f"Error while committing the record: {e}")
            raise Exception("An error occurred while committing the record to the database.")
        try:
            await session.refresh(record)
        except Exception as e:
            logger.error(f"Error while refreshing the record: {e}")
            raise Exception("An error occurred while refreshing the record.")
        try:
            await self.after_create_commit(session, record=record, data=data, user=user)
        except Exception as e:
            logger.error(f"Error after committing the record: {e}")
            raise Exception("An error occurred after committing the record to the database.")
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
            logger.error(f"Error befor updating the record: {e}")
            raise Exception("An error occurred before updating the record.")
        try:
            record = await self.update_draft(session, id=id, data=data, user=user)
        except Exception as e:
            logger.error(f"Error while updating the record: {e}")
            raise Exception("An error occurred while updating the record.")
        try:
            await self.after_update(session, data=data, record=record, id=id, user=user)
        except Exception as e:
            logger.error(f"Error after updating the record: {e}")
            raise Exception("An error occurred after updating the record.")
        await session.commit()
        await session.refresh(record)
        try:
            await self.after_update_commit(
                session, data=data, record=record, id=id, user=user
            )
        except Exception as e:
            logger.error(f"Error after committing the record: {e}")
            raise Exception("An error occurred after committing the record to the database.")
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
        try:
            await self.before_delete(session, id=id, record=record)
        except Exception as e:
            logger.error(f"Error before deleting the record: {e}")
            raise Exception("An error occurred before deleting the record.")
        try:
            await self.delete_draft(session, id=id, record=record)
        except Exception as e:
            logger.error(f"Error while deleting the record: {e}")
            raise Exception("An error occurred while deleting the record.")
        try:
            await session.commit()
        except Exception as e:
            logger.error(f"Error while committing the deletion: {e}")
            raise Exception("An error occurred while committing the deletion.")
        try:
            await self.after_delete(session, id=id, record=record)
        except Exception as e:
            logger.error(f"Error after deleting the record: {e}")
            raise Exception("An error occurred after deleting the record.")

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
                logger.error(f"The record with id {id} does not exist.")
                raise Exception("The record doesn't exists.")
            try:
                await self.delete_draft(session, id=id, record=record)
            except Exception as e:
                logger.error(f"Error while deleting the record with id {id}: {e}")
                raise Exception("An error occurred while deleting the record.")
        try:
            await session.commit()
        except Exception as e:
            logger.error(f"Error while committing the deletion: {e}")
            raise Exception("An error occurred while committing the deletion.")