import datetime
import functools
import logging
import uuid
from hashlib import md5
from typing import Any, Generic, TypeVar

from sqlalchemy.dialects import postgresql
from sqlmodel import SQLModel, func, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel.sql.expression import SelectOfScalar

from app.features.user.models.user import User
from app.outbox.registry import outbox_registry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ModelType = TypeVar("ModelType", bound=SQLModel)
UserType = TypeVar("UserType", bound=User)
CreateSchemaType = TypeVar("CreateSchemaType", bound=SQLModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=SQLModel)


class RecordNotFoundError(Exception):
    """Raised when a record is not found."""

    pass


class PermissionDeniedError(Exception):
    """Raised when a user doesn't have required permissions."""

    pass


class CrudOperationError(Exception):
    """Specific exception for CRUD operations with error context."""

    pass


def track_crud_operation(func=None, *, step_name=None):
    """
    Decorator that tracks CRUD operations and handles their exceptions.
    Can be used with or without arguments.

    Usage:
        @track_crud_operation
        async def my_func(): ...

        @track_crud_operation(step_name="custom_name")
        async def my_func(): ...
    """

    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            operation_name = step_name or fn.__name__
            try:
                return await fn(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in {operation_name}: {e}", exc_info=True)
                new_exception = CrudOperationError(
                    f"Error during {operation_name}: {str(e)}"
                )
                raise new_exception from e  # Preserves original stack trace

        return wrapper

    # Handle both @track_crud_operation and @track_crud_operation()
    if func is None:
        # Called with arguments: @track_crud_operation(step_name="...")
        return decorator
    else:
        # Called without arguments: @track_crud_operation
        return decorator(func)


class OutboxEvent:
    create = True
    update = True
    delete = True


class CrudBase(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    def __init__(
        self,
        *,
        model: type[ModelType],
        schema_create: type[CreateSchemaType],
        schema_update: type[UpdateSchemaType],
        default_filter: Any | None = None,
        order_by: Any | None = None,
        outbox_events: dict[str, str] | None = None,
    ):
        """
        Initialize a CRUD handler for a specific model type.

        Args:
            model: The SQLModel class this CRUD handler will operate on
            schema_create: Pydantic schema for validating creation operations
            schema_update: Pydantic schema for validating update operations
            default_filter: Default filter to apply to queries (e.g., is_active=True)
            order_by: Default ordering for queries
            outbox_events: Mapping of event names to their corresponding payloads
        """
        self.model = model
        self.schema_create = schema_create
        self.schema_update = schema_update
        self.default_filter = default_filter
        self.order_by = order_by
        self.outbox_events = outbox_events or {}

    async def _safe_record_access(self, session: AsyncSession, record: ModelType):
        try:
            _ = record.id  # Teste l'accès à record
            return record
        except Exception:
            await session.refresh(record)
            return record

    async def _safe_commit_and_refresh(
        self,
        session: AsyncSession,
        record: ModelType | None = None,
        records: list[ModelType] | None = None,
        operation: str = "operation",
    ) -> None:
        """
        Commit la transaction et rafraîchit les records de manière sécurisée.

        Args:
            session: Session de base de données
            record: Record unique à rafraîchir (optionnel)
            records: Liste de records à rafraîchir (optionnel)
            operation: Nom de l'opération pour le logging
        """
        try:
            await session.commit()

            # Gérer les records individuels ou en liste
            records_to_refresh = []
            if record is not None:
                records_to_refresh.append(record)
            if records is not None:
                records_to_refresh.extend(records)

            # Rafraîchir chaque record de manière sécurisée
            for rec in records_to_refresh:
                if rec is not None:
                    await self._safe_record_refresh(session, rec)

        except Exception as e:
            logger.error(f"Error while committing {operation}: {e}")
            await session.rollback()
            raise CrudOperationError(f"Database error during {operation}: {str(e)}")

    async def _safe_record_refresh(
        self, session: AsyncSession, record: ModelType
    ) -> None:
        """
        Rafraîchit un record de manière sécurisée en vérifiant qu'il n'a pas été supprimé.

        Args:
            session: Session de base de données
            record: Record à rafraîchir
        """
        try:
            # Vérifier si le record est dans un état supprimé
            from sqlalchemy import inspect

            state = inspect(record)

            # Si le record a été supprimé, ne pas essayer de le rafraîchir
            if getattr(state, "deleted", False):
                logger.debug(
                    f"Record {record.__class__.__name__} with id {getattr(record, 'id', 'unknown')} was deleted, skipping refresh"
                )
                return

            # Si le record est persistant et pas supprimé, on peut le rafraîchir
            if getattr(state, "persistent", False):
                await session.refresh(record)
            else:
                logger.debug(
                    f"Record {record.__class__.__name__} is not persistent, skipping refresh"
                )

        except Exception as e:
            # Si le rafraîchissement échoue, c'est probablement que le record a été supprimé
            logger.warning(f"Failed to refresh record: {e}")
            # Ne pas lever d'exception car c'est un cas possible après un delete

    def _extract_data_dict(self, data) -> dict:
        """
        Extract dictionary from data, handling both SQLModel objects and dictionaries.

        Args:
            data: Either a SQLModel object with model_dump() or a dictionary

        Returns:
            Dictionary representation of the data
        """
        if hasattr(data, "model_dump"):
            return data.model_dump(exclude_unset=True)
        elif isinstance(data, dict):
            return dict(data)
        else:
            return {}

    def _serialize_for_json(self, data: dict) -> dict:
        """
        Serialize a dictionary to be JSON-compatible by converting datetime objects to ISO strings
        and UUID objects to strings.

        Args:
            data: Dictionary that may contain datetime or UUID objects

        Returns:
            Dictionary with datetime and UUID objects converted to strings
        """
        if not isinstance(data, dict):
            return data

        serialized = {}
        for key, value in data.items():
            if isinstance(value, datetime.datetime):
                serialized[key] = value.isoformat()
            elif isinstance(value, uuid.UUID):
                serialized[key] = str(value)
            elif isinstance(value, dict):
                serialized[key] = self._serialize_for_json(value)
            elif isinstance(value, list):
                serialized[key] = [
                    item.isoformat()
                    if isinstance(item, datetime.datetime)
                    else str(item)
                    if isinstance(item, uuid.UUID)
                    else self._serialize_for_json(item)
                    if isinstance(item, dict)
                    else item
                    for item in value
                ]
            else:
                serialized[key] = value
        return serialized

    def _build_outbox_payload(
        self,
        action: str,
        record: ModelType,
        user: UserType | None = None,
        data: dict | None = None,
    ) -> dict:
        """
        Build standardized outbox payload for events.

        Args:
            action: The action being performed ('create', 'update', 'delete')
            record: The record being operated on
            user: User performing the operation
            data: Additional data for create/update operations

        Returns:
            Standardized payload dictionary
        """
        payload = {
            "id": str(record.id),
            "model": self.model.__name__,
            "action": action,
            "user_id": str(user.id) if user else None,
            "timestamp": datetime.datetime.now().isoformat(),
        }

        if action in ["create", "update"] and data:
            payload["data"] = self._serialize_for_json(data)
        elif action == "delete":
            # For delete, keep only essential info to avoid serialization issues
            payload["data"] = {
                "id": str(record.id),
                "name": getattr(record, "name", None),
                "description": getattr(record, "description", None),
                "created_by_id": getattr(record, "created_by_id", None),
                # Add other critical fields if needed for handlers
            }

        return payload

    def get_query_identifier(self, statement: SelectOfScalar[ModelType]) -> str:
        """
        Generate a unique hash for a SQL statement for caching purposes.

        Args:
            statement: The SQLModel/SQLAlchemy statement to hash

        Returns:
            String hash (MD5) of the compiled SQL statement
        """
        statement = str(
            statement.compile(
                compile_kwargs={"literal_binds": True}, dialect=postgresql.dialect()
            )
        )
        return md5(str(statement).encode()).hexdigest()

    async def count(
        self, session: AsyncSession, statement: SelectOfScalar[ModelType]
    ) -> int:
        """
        Count the number of records matching a query statement.

        Args:
            session: Database session
            statement: Query statement to count results for

        Returns:
            Integer count of matching records

        Raises:
            CrudOperationError: If the count operation fails
        """
        count_statement = select(func.count()).select_from(statement.subquery())
        result = await session.exec(count_statement)
        return result.one()

    # Read Operations
    async def check_user_permission(
        self,
        session: AsyncSession,
        *,
        permission: str | None = None,
        user: UserType | None = None,
    ):
        return True

    async def read_after(
        self,
        session: AsyncSession,
        *,
        record: ModelType | None = None,
        user: UserType | None = None,
    ) -> None:
        """
        Trigger 'after read' events for a record.

        Args:
            session: Database session
            record: The record that was read
            user: User who performed the read operation

        Returns:
            None
        """
        await self.trigger_event(
            "read", "after", session=session, record=record, user=user
        )

    async def read(
        self,
        session: AsyncSession,
        *,
        id: uuid.UUID,
        user: UserType | None = None,
        read_event: bool = False,
    ) -> ModelType | Any:
        """
        Retrieve a single record by its ID.

        Args:
            session: Database session
            id: UUID of the record to retrieve
            user: User who is performing the read
            read_event: Whether to trigger read events

        Returns:
            The requested record

        Raises:
            RecordNotFoundError: If the record doesn't exist
        """
        record = await session.get(self.model, id)
        if not record:
            logger.error(f"The record with id {id} does not exist.")
            raise RecordNotFoundError("The record doesn't exist.")
        # To follow get_multi logic
        if read_event:
            await self.read_after(session, record=record, user=user)
        return record

    async def read_multi_statement(
        self,
        session: AsyncSession,
        *,
        skip: int = 0,
        limit: int = 0,
        ids: list[uuid.UUID] | None = None,
        include_archived: bool = False,
        include_all_admin: bool = False,
        filter: Any = None,
        order_by: Any | None = None,
    ) -> SelectOfScalar[ModelType]:
        """
        Build a query statement for retrieving multiple records.

        Args:
            session: Database session
            skip: Number of records to skip
            limit: Maximum number of records to return
            ids: Filter by specific record IDs
            include_all: Whether to include records that would be filtered by default_filter
            include_all_admin: Whether admin users should see all records
            filter: Additional filter criteria
            order_by: Ordering criteria (overrides default)

        Returns:
            SQLAlchemy select statement ready for execution
        """
        statement = select(self.model)
        if order_by is None:
            order_by = self.order_by
        if isinstance(order_by, tuple | list):
            statement = statement.order_by(*order_by)
        else:
            statement = statement.order_by(order_by)
        if ids and len(ids):
            statement = statement.where(self.model.id.in_(ids))  # type: ignore
        if include_archived is False and self.default_filter is not None:
            statement = statement.where(self.default_filter)
        if filter is not None:
            statement = statement.where(filter)
        return statement

    async def read_multi(
        self,
        session: AsyncSession,
        *,
        statement: SelectOfScalar[ModelType] | None = None,
        skip: int = 0,
        limit: int = 0,
        ids: list[uuid.UUID] | None = None,
        include_archived: bool = False,
        filter: Any = None,
        order_by: Any | None = None,
        user: UserType | None = None,
        read_event: bool = False,
    ) -> dict[str, Any]:
        """
        Retrieve multiple records with pagination.

        Args:
            session: Database session
            statement: Pre-built query statement (optional)
            skip: Number of records to skip
            limit: Maximum number of records to return
            ids: Filter by specific record IDs
            include_all: Whether to include records that would be filtered by default_filter
            filter: Additional filter criteria
            order_by: Ordering criteria (overrides default)
            user: User who is performing the read
            read_event: Whether to trigger read events for each record

        Returns:
            Dictionary with 'data' (list of records) and 'count' (total matching records)

        Raises:
            CrudOperationError: If the query fails
        """
        if statement is None:
            statement = await self.read_multi_statement(
                session,
                skip=skip,
                limit=limit,
                ids=ids,
                include_archived=include_archived,
                filter=filter,
                order_by=order_by,
            )
        statement_limited = statement
        if skip:
            statement_limited = statement_limited.offset(skip)
        if limit:
            statement_limited = statement_limited.limit(limit)
        logger.debug(f"SQL Query: {statement_limited}")
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
                await self.read_after(session, record=record, user=user)
        return {"data": data, "count": count}

    #
    # Create operations
    #

    @track_crud_operation
    async def before_create(
        self, session: AsyncSession, *, data: CreateSchemaType, user: UserType | None
    ) -> None:
        """
        Trigger 'before create' events.

        Args:
            session: Database session
            data: Creation data
            user: User performing the create operation

        Returns:
            None
        """
        pass

    @track_crud_operation
    async def after_create(
        self,
        session: AsyncSession,
        *,
        record: ModelType | None = None,
        data: CreateSchemaType,
        user: UserType | None,
    ) -> None:
        """
        Trigger 'after create' events.

        Args:
            session: Database session
            record: The newly created record
            data: Creation data used
            user: User who performed the create operation

        Returns:
            None
        """
        if "create" in self.outbox_events:
            await outbox_registry.publish(
                session,
                self.outbox_events["create"],
                {
                    "id": str(record.id),
                    "type": record.__class__.__name__,
                    "user_id": str(user.id) if user else None,
                },
            )

    @track_crud_operation
    async def after_create_commit(
        self,
        session: AsyncSession,
        *,
        record: ModelType | None = None,
        data: CreateSchemaType,
        user: UserType | None,
    ) -> None:
        """
        Trigger 'after create commit' events (after transaction is committed).

        Args:
            session: Database session
            record: The newly created record
            data: Creation data used
            user: User who performed the create operation

        Returns:
            None
        """
        pass

    async def create_draft(
        self,
        session: AsyncSession,
        *,
        data: CreateSchemaType,
        user: UserType | None,
    ) -> ModelType:
        """
        Create a new record without committing (for use in transactions).

        Args:
            session: Database session
            data: Creation data
            user: User performing the create operation

        Returns:
            The newly created record (not yet committed)

        Raises:
            CrudOperationError: If the creation fails
        """
        await self.before_create(session, data=data, user=user)

        # Extract data dictionary
        data_dict = self._extract_data_dict(data)
        data_dict["created_at"] = datetime.datetime.now()
        if user and user.id:
            data_dict["created_by_id"] = user.id
        record = self.model(**data_dict)
        session.add(record)
        await session.flush()

        # Publish outbox event after record is created and has an ID
        if self.outbox_events and "create" in self.outbox_events:
            payload = self._build_outbox_payload(
                action="create", record=record, user=user, data=data_dict
            )
            await outbox_registry.publish(
                session, f"create.{self.model.__name__.lower()}", payload
            )

        await self.after_create(session, record=record, data=data, user=user)
        return record

    async def create(
        self, session: AsyncSession, *, data: CreateSchemaType, user: UserType | None
    ) -> ModelType:
        """
        Create a new record and commit it to the database.

        Args:
            session: Database session
            data: Creation data
            user: User performing the create operation

        Returns:
            The newly created and committed record

        Raises:
            CrudOperationError: If the creation or commit fails
        """
        record = await self.create_draft(session, data=data, user=user)
        await self._safe_commit_and_refresh(session, record=record, operation="create")
        await self.after_create_commit(session, record=record, data=data, user=user)
        return record

    async def create_multiple(
        self,
        session: AsyncSession,
        *,
        data: list[CreateSchemaType],
        user: UserType | None,
    ) -> list[ModelType]:
        """
        Create multiple records without committing (for use in transactions).

        Args:
            session: Database session
            data: List of creation data objects
            user: User performing the create operation

        Returns:
            List of newly created records (not yet committed)

        Raises:
            CrudOperationError: If any creation fails
        """
        records = []
        for item in data:
            record = await self.create_draft(session, data=item, user=user)
            records.append(record)
        return records

    async def create_multiple_commit(
        self,
        session: AsyncSession,
        *,
        data: list[CreateSchemaType],
        user: UserType | None,
    ) -> list[ModelType]:
        """
        Create multiple records and commit them to the database.

        Args:
            session: Database session
            data: List of creation data objects
            user: User performing the create operation

        Returns:
            List of newly created and committed records

        Raises:
            CrudOperationError: If any creation or the commit fails
        """
        records = await self.create_multiple(session, data=data, user=user)
        await self._safe_commit_and_refresh(
            session, records=records, operation="create_multiple_commit"
        )
        return records

    # Update operations

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
        """
        Trigger 'before update' events.

        Args:
            session: Database session
            data: Update data
            record: The record being updated (optional)
            id: ID of the record being updated (optional)
            user: User performing the update operation

        Returns:
            None
        """
        pass

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
        """
        Trigger 'after update' events.

        Args:
            session: Database session
            data: Update data used
            record: The updated record
            id: ID of the record updated
            user: User who performed the update operation

        Returns:
            None
        """
        if "update" in self.outbox_events:
            await outbox_registry.publish(
                session,
                self.outbox_events["update"],
                {
                    "id": str(record.id),
                    "type": record.__class__.__name__,
                    "user_id": str(user.id) if user else None,
                },
            )

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
        """
        Trigger 'after update commit' events (after transaction is committed).

        Args:
            session: Database session
            data: Update data used
            record: The updated record
            id: ID of the record updated
            user: User who performed the update operation

        Returns:
            None
        """
        pass

    async def update_draft(
        self,
        session: AsyncSession,
        *,
        id: uuid.UUID,
        data: UpdateSchemaType,
        user: UserType | None = None,
        record: ModelType | None = None,
    ) -> ModelType:
        """
        Update a record without committing (for use in transactions).

        Args:
            session: Database session
            id: ID of the record to update
            data: Update data
            user: User performing the update operation
            record: Pre-fetched record (optional, to avoid another database lookup)

        Returns:
            The updated record (not yet committed)

        Raises:
            RecordNotFoundError: If the record doesn't exist
            CrudOperationError: If the update fails
        """
        await self.before_update(session, data=data, record=record, id=id, user=user)
        if not record:
            record = await session.get(self.model, id)

        # Ensure record exists before proceeding
        if not record:
            logger.error(f"The record with id {id} does not exist.")
            raise RecordNotFoundError("The record doesn't exist.")

        # Publish outbox event after record is confirmed to exist
        if self.outbox_events and "update" in self.outbox_events:
            payload_data = self._extract_data_dict(data)
            payload = self._build_outbox_payload(
                action="update", record=record, user=user, data=payload_data
            )
            await outbox_registry.publish(
                session, f"update.{self.model.__name__.lower()}", payload
            )

        # Extract and apply updates
        data_dict = self._extract_data_dict(data)
        data_dict["modify_at"] = datetime.datetime.now()
        if user and user.id:
            data_dict["modify_by_id"] = user.id
        for key in data_dict.keys():
            if hasattr(record, key):
                setattr(record, key, data_dict[key])
        await self.after_update(session, data=data, record=record, id=id, user=user)
        return record

    async def update(
        self,
        session: AsyncSession,
        *,
        id: uuid.UUID,
        data: UpdateSchemaType,
        user: UserType | None = None,
        record: ModelType | None = None,
    ) -> ModelType:
        """
        Update a record and commit it to the database.

        Args:
            session: Database session
            id: ID of the record to update
            data: Update data
            user: User performing the update operation
            record: Pre-fetched record (optional, to avoid another database lookup)

        Returns:
            The updated and committed record

        Raises:
            RecordNotFoundError: If the record doesn't exist
            CrudOperationError: If the update or commit fails
        """
        record = await self.update_draft(
            session, id=id, data=data, user=user, record=record
        )
        await self._safe_commit_and_refresh(session, record=record, operation="update")
        await self.after_update_commit(session, data=data, record=record, user=user)
        return record

    class UpdateItem(SQLModel):
        """
        Helper model for update_multi operations that pairs an ID with update data.
        """

        id: uuid.UUID
        data: UpdateSchemaType

    async def update_multi(
        self,
        session: AsyncSession,
        *,
        items: list[UpdateItem],
        user: UserType | None = None,
    ) -> list[ModelType]:
        """
        Update multiple records without committing (for use in transactions).

        Args:
            session: Database session
            items: List of UpdateItem objects (each with id and data)
            user: User performing the update operation

        Returns:
            List of updated records (not yet committed)

        Raises:
            RecordNotFoundError: If any record doesn't exist
            CrudOperationError: If any update fails
        """
        records = []
        for item in items:
            record = await self.update_draft(
                session, id=item.id, data=item.data, user=user
            )
            records.append(record)
        return records

    async def update_multi_commit(
        self,
        session: AsyncSession,
        *,
        items: list[UpdateItem],
        user: UserType | None = None,
    ) -> list[ModelType]:
        """
        Update multiple records and commit them to the database.

        Args:
            session: Database session
            items: List of UpdateItem objects (each with id and data)
            user: User performing the update operation

        Returns:
            List of updated and committed records

        Raises:
            RecordNotFoundError: If any record doesn't exist
            CrudOperationError: If any update or the commit fails
        """
        records = await self.update_multi(session, items=items, user=user)
        await self._safe_commit_and_refresh(
            session, records=records, operation="update_multi_commit"
        )
        return records

    # Delete operations

    @track_crud_operation
    async def before_delete(
        self,
        session: AsyncSession,
        *,
        id: uuid.UUID,
        record: ModelType | None = None,
        user: UserType | None = None,
    ) -> None:
        """
        Trigger 'before delete' events.

        Args:
            session: Database session
            id: ID of the record being deleted
            record: The record being deleted (optional)
            user: User performing the delete operation

        Returns:
            None
        """
        pass

    @track_crud_operation
    async def after_delete(
        self,
        session: AsyncSession,
        *,
        id: uuid.UUID,
        record: ModelType | None = None,
        user: UserType | None = None,
    ) -> None:
        """
        Trigger 'after delete' events.

        Args:
            session: Database session
            id: ID of the deleted record
            record: The deleted record (before deletion)
            user: User who performed the delete operation

        Returns:
            None
        """
        if "delete" in self.outbox_events:
            await outbox_registry.publish(
                session,
                self.outbox_events["delete"],
                {
                    "id": str(record.id),
                    "type": record.__class__.__name__,
                    "user_id": str(user.id) if user else None,
                },
            )

    @track_crud_operation
    async def after_delete_commit(
        self,
        session: AsyncSession,
        *,
        id: uuid.UUID | None = None,
        ids: list[uuid.UUID] | None = None,
        user: UserType | None = None,
    ) -> None:
        """
        Trigger 'after delete commit' events (after transaction is committed).

        Args:
            session: Database session
            id: ID of the deleted record (for single deletes)
            ids: IDs of deleted records (for multi deletes)
            user: User who performed the delete operation

        Returns:
            None
        """
        pass

    async def delete_draft(
        self,
        session: AsyncSession,
        *,
        id: uuid.UUID,
        record: ModelType | None = None,
        user: UserType | None = None,
    ) -> None:
        """
        Delete a record without committing (for use in transactions).

        Args:
            session: Database session
            id: ID of the record to delete
            record: Pre-fetched record (optional, to avoid another database lookup)
            user: User performing the delete operation

        Returns:
            True if successful

        Raises:
            RecordNotFoundError: If the record doesn't exist
            CrudOperationError: If the deletion fails
        """
        await self.before_delete(session, id=id, record=record, user=user)
        if not record:
            record = await session.get(self.model, id)
        if not record:
            logger.error(f"The record with id {id} does not exist.")
            raise RecordNotFoundError("The record doesn't exist.")
        if self.outbox_events and "delete" in self.outbox_events:
            payload = self._build_outbox_payload(
                action="delete",
                record=record,
                user=user,
                # No data parameter - handled by the helper method
            )
            await outbox_registry.publish(
                session, f"delete.{self.model.__name__.lower()}", payload
            )
        await session.delete(record)
        await self.after_delete(session, id=id, record=record, user=user)
        return True

    async def delete(
        self,
        session: AsyncSession,
        *,
        id: uuid.UUID,
        record: ModelType | None = None,
        user: UserType | None = None,
    ) -> bool:
        """
        Delete a record and commit the deletion to the database.

        Args:
            session: Database session
            id: ID of the record to delete
            record: Pre-fetched record (optional, to avoid another database lookup)
            user: User performing the delete operation

        Returns:
            True if successful

        Raises:
            RecordNotFoundError: If the record doesn't exist
            CrudOperationError: If the deletion or commit fails
        """
        await self.delete_draft(session, id=id, record=record, user=user)
        await self._safe_commit_and_refresh(session, record=record, operation="delete")
        await self.after_delete_commit(session, id=id, user=user)
        return True

    async def delete_multi(
        self,
        session: AsyncSession,
        *,
        ids: list[uuid.UUID],
        user: UserType | None = None,
    ) -> None:
        """
        Delete multiple records without committing (for use in transactions).

        Args:
            session: Database session
            ids: List of IDs to delete
            user: User performing the delete operation

        Returns:
            None

        Raises:
            RecordNotFoundError: If any record doesn't exist
            CrudOperationError: If any deletion fails
        """
        for id in ids:
            record = await self.read(session, id=id)
            if not record:
                logger.error(f"The record with id {id} does not exist.")
                raise RecordNotFoundError("The record doesn't exist.")
            await self.delete_draft(session, id=id, record=record, user=user)

    async def delete_multi_commit(
        self,
        session: AsyncSession,
        *,
        ids: list[uuid.UUID],
        user: UserType | None = None,
    ) -> None:
        """
        Delete multiple records and commit the deletions to the database.

        Args:
            session: Database session
            ids: List of IDs to delete
            user: User performing the delete operation

        Returns:
            None

        Raises:
            RecordNotFoundError: If any record doesn't exist
            CrudOperationError: If any deletion or the commit fails
        """
        await self.delete_multi(session, ids=ids, user=user)
        await self._safe_commit_and_refresh(
            session, record=None, operation="delete_multi_commit"
        )
        await self.after_delete_commit(session, ids=ids, user=user)
