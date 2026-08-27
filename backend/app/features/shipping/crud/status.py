"""
CRUD for status definitions and transitions.
"""

from sqlmodel import and_, col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.shipping.models.status import (
    StatusDefinition,
    StatusDefinitionCreate,
    StatusDefinitionUpdate,
    StatusTransition,
    StatusTransitionCreate,
    StatusTransitionUpdate,
)


class StatusDefinitionCrud(
    CrudBase[StatusDefinition, StatusDefinitionCreate, StatusDefinitionUpdate]
):
    """Represents status definition crud."""

    async def get_by_code(
        self,
        session: AsyncSession,
        entity: str,
        code: str,
    ) -> StatusDefinition | None:
        """Retrieve a status by entity and code"""
        statement = select(StatusDefinition).where(
            StatusDefinition.entity == entity,
            StatusDefinition.code == code,
            col(StatusDefinition.is_active).is_(True),
        )

        result = await session.exec(statement)
        return result.first()

    async def get_by_entity(
        self,
        session: AsyncSession,
        entity: str,
    ) -> list[StatusDefinition]:
        """Retrieve all statuses for an entity"""

        statement = (
            select(StatusDefinition)
            .where(
                and_(
                    StatusDefinition.entity == entity,
                    col(StatusDefinition.is_active).is_(True),
                )
            )
            .order_by(
                col(StatusDefinition.sequence_order).asc(),
                col(StatusDefinition.name).asc(),
            )
        )

        result = await session.exec(statement)
        return list(result.all())

    async def get_terminal_statuses(
        self,
        session: AsyncSession,
        entity: str,
    ) -> list[StatusDefinition]:
        """Get terminal statuses."""

        statement = (
            select(StatusDefinition)
            .where(
                and_(
                    StatusDefinition.entity == entity,
                    col(StatusDefinition.is_terminal).is_(True),
                    col(StatusDefinition.is_active).is_(True),
                )
            )
            .order_by(col(StatusDefinition.sequence_order).asc())
        )

        result = await session.exec(statement)
        return list(result.all())


class StatusTransitionCrud(
    CrudBase[StatusTransition, StatusTransitionCreate, StatusTransitionUpdate]
):
    """Represents status transition crud."""

    async def get_transitions_from_status(
        self,
        session: AsyncSession,
        entity: str,
        from_code: str,
    ) -> list[StatusTransition]:
        """Retrieve possible transitions from a status"""

        statement = select(StatusTransition).where(
            and_(
                StatusTransition.entity == entity,
                StatusTransition.from_code == from_code,
                col(StatusTransition.is_active).is_(True),
            )
        )

        result = await session.exec(statement)
        return list(result.all())

    async def get_transitions_to_status(
        self,
        session: AsyncSession,
        entity: str,
        to_code: str,
    ) -> list[StatusTransition]:
        """Get transitions to status."""

        statement = select(StatusTransition).where(
            and_(
                StatusTransition.entity == entity,
                StatusTransition.to_code == to_code,
                col(StatusTransition.is_active).is_(True),
            )
        )

        result = await session.exec(statement)
        return list(result.all())

    async def get_auto_transitions(
        self,
        session: AsyncSession,
        entity: str,
    ) -> list[StatusTransition]:
        """Get auto transitions."""

        statement = select(StatusTransition).where(
            and_(
                StatusTransition.entity == entity,
                col(StatusTransition.auto_advance).is_(True),
                col(StatusTransition.is_active).is_(True),
            )
        )

        result = await session.exec(statement)
        return list(result.all())

    async def is_transition_allowed(
        self,
        session: AsyncSession,
        entity: str,
        from_code: str,
        to_code: str,
    ) -> bool:
        """Check whether transition allowed."""

        statement = select(StatusTransition).where(
            and_(
                StatusTransition.entity == entity,
                StatusTransition.from_code == from_code,
                StatusTransition.to_code == to_code,
                col(StatusTransition.is_active).is_(True),
            )
        )

        result = await session.exec(statement)
        return result.first() is not None


crud_status_definition = StatusDefinitionCrud(
    model=StatusDefinition,
    schema_create=StatusDefinitionCreate,
    schema_update=StatusDefinitionUpdate,
    default_filter=and_(
        col(StatusDefinition.is_active).is_(True),
    ),
    order_by=col(StatusDefinition.sequence_order).asc(),
)

crud_status_transition = StatusTransitionCrud(
    model=StatusTransition,
    schema_create=StatusTransitionCreate,
    schema_update=StatusTransitionUpdate,
    default_filter=and_(
        col(StatusTransition.is_active).is_(True),
    ),
)
