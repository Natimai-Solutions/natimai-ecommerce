import datetime
import functools
import importlib
import logging
import uuid
from hashlib import md5
from typing import Any, Generic, TypeVar

from sqlalchemy.dialects import postgresql
from sqlmodel import SQLModel, func, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel.sql.expression import SelectOfScalar

from backend.app.api.user.model.user import User

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

class CrudOperationError(Exception):
    """Exception spécifique pour les opérations CRUD avec contexte de l'erreur."""
    pass

def track_crud_operation(func=None, *, step_name=None):
    """
    Décorateur qui trace les opérations CRUD et gère leurs exceptions.
    Peut être utilisé avec ou sans arguments.
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            operation_name = step_name or func.__name__
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in {operation_name}: {e}", exc_info=True)
                new_exception = CrudOperationError(f"Error during {operation_name}: {str(e)}")
                raise new_exception from e  # Préserve la stack trace d'origine
        return wrapper
    return decorator


class CrudBase(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    def __init__(
        self,
        *,
        model: type[ModelType],
        schema_create: type[CreateSchemaType],
        schema_update: type[UpdateSchemaType],
        default_filter: Any | None = None,
        order_by: Any | None = None,
        allow_all_user_to_create: bool = False
    ):
        self.model = model
        self.schema_create = schema_create
        self.schema_update = schema_update
        self.default_filter = default_filter
        self.order_by = order_by
        self.allow_all_user_to_create = allow_all_user_to_create
        self.event_handlers = {
            "create": {"before": [], "after": [], "after_commit": []},
            "read": {"after": []},
            "update": {"before": [], "after": [], "after_commit": []},
            "delete": {"before": [], "after": []},
            # Pour conserver la compatibilité avec les événements spécifiques
            "custom": {},
        }

    def register_event_handler(
        self, 
        operation: str, 
        phase: str | callable = None, 
        handler_func: callable = None,
    ):
        """
        Registers a handler for a specific event.

        The handler will always receive these parameters (some may be None):
            - session: AsyncSession - The active database session
            - user: User | None - The user who triggered the operation
            - record: ModelType | None - The affected record (after creation/update)
            - data: CreateSchemaType | UpdateSchemaType | None - The provided data
            - id: uuid.UUID | None - The record ID if applicable

        Args:
            operation: Type of operation ('create', 'read', 'update', 'delete') or custom event name
            phase: Phase of the operation ('before', 'after', 'after_commit')
            handler_func: Function to execute
        """
        # Support pour format register_event_handler(operation, handler_func)
        if phase is not None and handler_func is None and callable(phase):
            handler_func = phase
            if operation in self.event_handlers:
                # Considère qu'il s'agit d'un événement standard, par défaut "after"
                phase = "after"
            else:
                # C'est un événement personnalisé
                phase = operation
                operation = "custom"
        
        # Vérifie si c'est un événement CRUD standard
        if operation in ["create", "read", "update", "delete"]:
            if phase not in ["before", "after", "after_commit"]:
                phase = "after"
            
            self.event_handlers[operation][phase].append(handler_func)
        else:
            # Événement personnalisé
            if operation not in self.event_handlers["custom"]:
                self.event_handlers["custom"][operation] = []
            self.event_handlers["custom"][operation].append(handler_func)
        
        return self  # Pour le chaînage

    async def trigger_event(self, operation: str, phase: str = None, **context):
        """
        Triggers all handlers associated with an event.

        Args:
            operation: Type of operation ('create', 'read', 'update', 'delete') or event name
            phase: Phase of the operation ('before', 'after', 'after_commit')
            **context: Context to pass to the handlers
        """

        standard_context = {
            "session": context.get("session"),
            "record": context.get("record"),
            "data": context.get("data"),
            "user": context.get("user"),
            "id": context.get("id"),
        }

        for key, value in context.items():
            if key not in standard_context:
                standard_context[key] = value

        handlers = []

        if operation in self.event_handlers and phase in self.event_handlers[operation]:
            # Format nouveau: opération CRUD standard
            handlers = self.event_handlers[operation][phase]
        elif operation in self.event_handlers["custom"]:
            handlers = self.event_handlers["custom"][operation]
        else:
            logger.debug(f"Aucun handler pour l'opération {operation}, phase {phase}")
            return

        # Exécuter les handlers
        if not handlers:
            return
            
        logger.debug(f"Exécution de {len(handlers)} handlers pour {operation}/{phase}")
        for handler in handlers:
            try:
                result = handler(**standard_context)
                if hasattr(result, '__await__'):
                    await result
            except Exception as e:
                logger.error(f"Erreur dans le handler pour {operation}/{phase}: {e}")
                # Ne pas propager l'erreur pour ne pas bloquer le flux principal

    async def _safe_commit_and_refresh(self, session: AsyncSession, record: ModelType, operation: str = "operation") -> None:
        try:
            await session.commit()
            await session.refresh(record)
        except Exception as e:
            logger.error(f"Error while committing {operation}: {e}")
            raise CrudOperationError(f"Database error during {operation}: {str(e)}")

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

    async def read_after(
        self,
        session: AsyncSession,
        *,
        record: ModelType | None = None,
        user: UserType | None = None,
    ) -> None:
        self.register_event_handler(
            "read", "after", session=session, record=record, user=user
        )

    async def get(
        self,
        session: AsyncSession,
        *,
        id: uuid.UUID,
        user: UserType | None = None,
        read_event: bool = False,
    ) -> ModelType | Any:
        record = await session.get(self.model, id)
        if not record:
            logger.error(f"The record with id {id} does not exist.")
            raise RecordNotFoundError("The record doesn't exists.")
        # To follow get_multi logic
        if read_event:
            await self.read_after(session, record=record, user=user)
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
        read_event: bool = False,
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
            raise CrudOperationError("An error occurred while counting the records.")
        try:
            result = await session.exec(statement_limited)
            data = result.all()
        except Exception as e:
            logger.error(f"Error while executing the query: {e}")
            raise CrudOperationError("An error occurred while executing the query.")
        # Seems heavy, so we should use it only when needed
        if read_event:
            for record in data:
                self.read_after(session, record=record, user=user)
        return {"data": data, "count": count}

    @track_crud_operation
    async def create_draft(
        self, session: AsyncSession, *, data: CreateSchemaType, user: UserType | None
    ) -> ModelType:
        data_dict = data.model_dump(exclude_unset=True)
        record = self.model(**data_dict)
        session.add(record)
        await session.flush()
        await session.refresh(record)
        return record

    @track_crud_operation
    async def before_create(
        self, session: AsyncSession, *, data: CreateSchemaType, user: UserType | None
    ) -> None:
        await self.trigger_event("create", "before", session=session, data=data, user=user)
    
    @track_crud_operation
    async def after_create(
        self,
        session: AsyncSession,
        *,
        record: ModelType | None = None,
        data: CreateSchemaType,
        user: UserType | None,
    ) -> None:
        await self.trigger_event("create", "after", session=session, record=record, data=data, user=user)
    
    @track_crud_operation
    async def after_create_commit(
        self,
        session: AsyncSession,
        *,
        record: ModelType | None = None,
        data: CreateSchemaType,
        user: UserType | None,
    ) -> None:
        await self.trigger_event("create", "after_commit", session=session, record=record, data=data, user=user)
    
    async def create(
        self,
        session: AsyncSession,
        *,
        data: CreateSchemaType,
        user: UserType | None,
    ) -> ModelType:
        await self.before_create(session, data=data, user=user)
        record = await self.create_draft(session, data=data, user=user)
        await self.after_create(session, record=record, data=data, user=user)
        await self._safe_commit_and_refresh(session, record, operation="create")
        await self.after_create_commit(session, record=record, data=data, user=user)
        return record

    @track_crud_operation
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
        for key in data_dict.keys():
            if hasattr(record, key):
                setattr(record, key, data_dict[key])
        return record

    @track_crud_operation
    async def before_update(
        self,
        session: AsyncSession,
        *,
        data: UpdateSchemaType | None,
        record: ModelType | None = None,
        id: uuid.UUID | None = None,
        user: UserType | None = None,
    ) -> None:
        await self.trigger_event("update", "before", session=session, data=data, user=user)

    @track_crud_operation
    async def after_update(
        self,
        session: AsyncSession,
        *,
        data: UpdateSchemaType | None,
        record: ModelType | None = None,
        id: uuid.UUID | None = None,
        user: UserType | None,
    ) -> None:
        await self.trigger_event("update", "after", session=session, data=data, user=user)
    
    @track_crud_operation
    async def after_update_commit(
        self,
        session: AsyncSession,
        *,
        data: UpdateSchemaType | None,
        record: ModelType | None = None,
        id: uuid.UUID | None = None,
        user: UserType | None = None,
    ) -> None:
        await self.trigger_event("create", "after_commit", session=session, data=data, user=user)


    async def update(
        self,
        session: AsyncSession,
        *,
        id: uuid.UUID,
        data: UpdateSchemaType,
        user: UserType | None = None,
        record: ModelType | None = None,
    ) -> ModelType:
        await self.before_update(
            session, data=data, record=record, id=id, user=user
        )
        record = await self.update_draft(session, id=id, data=data, user=user)
        await self.after_update(session, data=data, record=record, id=id, user=user)
        
        await self._safe_commit_and_refresh(session, record, operation="update")
        
        await self.after_update_commit(
                session, data=data, record=record, id=id, user=user
            )
        return record

    @track_crud_operation
    async def delete_draft(
        self, session: AsyncSession, *, id: uuid.UUID, record: ModelType | None = None
    ) -> None:
        if not record:
            record = await session.get(self.model, id)
        if not record:
            logger.error(f"The record with id {id} does not exist.")
            raise RecordNotFoundError("The record doesn't exists.")
        await session.delete(record)

    @track_crud_operation
    async def before_delete(
        self, session: AsyncSession, *, id: uuid.UUID, record: ModelType | None = None, user: UserType | None = None
    ) -> None:
        await self.trigger_event("delete", "before", session=session, record=record, user=user)

    @track_crud_operation
    async def after_delete(
        self, session: AsyncSession, *, id: uuid.UUID, record: ModelType | None = None, user: UserType | None = None
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
        await self.before_delete(session, id=id, record=record, user=user)
        await self.delete_draft(session, id=id, record=record, user=user)
        try:
            await session.commit()
        except Exception as e:
            logger.error(f"Error while committing the deletion: {e}")
            raise CrudOperationError(f"An error occurred while committing the deletion: {str(e)}")
        await self.after_delete(session, id=id, record=record, user=user)

    async def delete_multi(
        self,
        session: AsyncSession,
        *,
        ids: list[uuid.UUID],
        user: UserType | None = None,
    ) -> None:
        async with session.begin_nested():
            for id in ids:
                record = await self.get(session, id=id)
                if not record:
                    logger.error(f"The record with id {id} does not exist.")
                    raise RecordNotFoundError("The record doesn't exists.")
                await self.before_delete(session, id=id, record=record, user=user)
                await self.delete_draft(session, id=id, record=record)
                await self.after_delete(session, ids=ids, user=user)
        try:
            await session.commit()
        except Exception as e:
            logger.error(f"Error while committing the deletion: {e}")
            raise CrudOperationError(f"An error occurred while committing the deletion: {str(e)}")