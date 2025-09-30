"""
Modèles de statuts configurables.
Système flexible de statuts et transitions.
"""

import uuid

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class StatusDefinitionBase(Base):
    """Catalogue de statuts par type d'entité (souple, extensible)"""

    entity: str = Field(
        max_length=50,
        description="Type d'entité: route, step, consolidation, delivery_task, order_step",
    )
    code: str = Field(
        max_length=50,
        description="Code du statut: draft, ready, dispatched, in_transit, arrived, closed",
    )
    name: str = Field(max_length=100, description="Nom affichable du statut")
    description: str | None = Field(
        default=None, max_length=500, description="Status description"
    )
    rank: int = Field(default=0, description="Display order")
    is_terminal: bool = Field(
        default=False, description="Statut terminal (fin de processus)"
    )

    # Personnalisation UI
    ui_color: str | None = Field(
        default=None, max_length=20, description="Couleur pour l'interface"
    )
    ui_icon: str | None = Field(
        default=None, max_length=50, description="Icône pour l'interface"
    )


class StatusDefinition(StatusDefinitionBase, table=True):
    """Catalogue de statuts par type d'entité (souple, extensible)"""

    __tablename__ = "status_definitions"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True),
    )


class StatusDefinitionCreate(StatusDefinitionBase, BaseCreate):
    pass


class StatusDefinitionUpdate(StatusDefinitionBase, BaseUpdate):
    entity: str | None = None
    code: str | None = None
    name: str | None = None
    description: str | None = None
    rank: int | None = None
    is_terminal: bool | None = None
    ui_color: str | None = None
    ui_icon: str | None = None


class StatusDefinitionPublic(StatusDefinitionBase, BasePublic):
    id: uuid.UUID


class StatusTransitionBase(Base):
    """Transitions autorisées entre statuts (les gardes sont codées côté service)"""

    entity: str = Field(max_length=50, description="Type d'entité")
    from_code: str = Field(max_length=50, description="Source status")
    to_code: str = Field(max_length=50, description="Target status")
    guard_name: str | None = Field(
        default=None, max_length=100, description="Nom de la garde métier"
    )
    auto_advance: bool = Field(default=False, description="Automatic transition")

    # Conditions
    requires_confirmation: bool = Field(
        default=False, description="Nécessite une confirmation"
    )
    requires_scan: bool = Field(default=False, description="Nécessite un scan")


class StatusTransition(StatusTransitionBase, table=True):
    """Transitions autorisées entre statuts"""

    __tablename__ = "status_transitions"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True),
    )


class StatusTransitionCreate(StatusTransitionBase, BaseCreate):
    pass


class StatusTransitionUpdate(StatusTransitionBase, BaseUpdate):
    entity: str | None = None
    from_code: str | None = None
    to_code: str | None = None
    guard_name: str | None = None
    auto_advance: bool | None = None
    requires_confirmation: bool | None = None
    requires_scan: bool | None = None


class StatusTransitionPublic(StatusTransitionBase, BasePublic):
    id: uuid.UUID


class StatusDefinitionsPublic(SQLModel):
    data: list[StatusDefinitionPublic] = Field(
        default_factory=list,
        description="List of status definitions",
    )
    count: int = Field(
        default=0,
        description="Total number of status definitions",
    )


class StatusTransitionsPublic(SQLModel):
    data: list[StatusTransitionPublic] = Field(
        default_factory=list,
        description="List of status transitions",
    )
    count: int = Field(
        default=0,
        description="Total number of status transitions",
    )
