"""
CRUD for status definitions and transitions.
"""


from sqlmodel import and_, select
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
            StatusDefinition.is_active.is_(True),
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
                    StatusDefinition.is_active.is_(True),
                )
            )
            .order_by(StatusDefinition.rank.asc(), StatusDefinition.name.asc())
        )

        result = await session.exec(statement)
        return result.all()

    async def get_terminal_statuses(
        self,
        session: AsyncSession,
        entity: str,
    ) -> list[StatusDefinition]:
        """Récupère les statuts terminaux d'une entité"""

        statement = (
            select(StatusDefinition)
            .where(
                and_(
                    StatusDefinition.entity == entity,
                    StatusDefinition.is_terminal.is_(True),
                    StatusDefinition.is_active.is_(True),
                )
            )
            .order_by(StatusDefinition.rank.asc())
        )

        result = await session.exec(statement)
        return result.all()


class StatusTransitionCrud(
    CrudBase[StatusTransition, StatusTransitionCreate, StatusTransitionUpdate]
):
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
                StatusTransition.is_active.is_(True),
            )
        )

        result = await session.exec(statement)
        return result.all()

    async def get_transitions_to_status(
        self,
        session: AsyncSession,
        entity: str,
        to_code: str,
    ) -> list[StatusTransition]:
        """Récupère les transitions menant à un statut"""

        statement = select(StatusTransition).where(
            and_(
                StatusTransition.entity == entity,
                StatusTransition.to_code == to_code,
                StatusTransition.is_active.is_(True),
            )
        )

        result = await session.exec(statement)
        return result.all()

    async def get_auto_transitions(
        self,
        session: AsyncSession,
        entity: str,
    ) -> list[StatusTransition]:
        """Récupère les transitions automatiques d'une entité"""

        statement = select(StatusTransition).where(
            and_(
                StatusTransition.entity == entity,
                StatusTransition.auto_advance.is_(True),
                StatusTransition.is_active.is_(True),
            )
        )

        result = await session.exec(statement)
        return result.all()

    async def is_transition_allowed(
        self,
        session: AsyncSession,
        entity: str,
        from_code: str,
        to_code: str,
    ) -> bool:
        """Vérifie si une transition est autorisée"""

        statement = select(StatusTransition).where(
            and_(
                StatusTransition.entity == entity,
                StatusTransition.from_code == from_code,
                StatusTransition.to_code == to_code,
                StatusTransition.is_active.is_(True),
            )
        )

        result = await session.exec(statement)
        return result.first() is not None


crud_status_definition = StatusDefinitionCrud(
    model=StatusDefinition,
    schema_create=StatusDefinitionCreate,
    schema_update=StatusDefinitionUpdate,
    default_filter=and_(
        StatusDefinition.is_active.is_(True),
    ),
    order_by=StatusDefinition.rank.asc(),
)

crud_status_transition = StatusTransitionCrud(
    model=StatusTransition,
    schema_create=StatusTransitionCreate,
    schema_update=StatusTransitionUpdate,
    default_filter=and_(
        StatusTransition.is_active.is_(True),
    ),
)

