"""
Configurable status models.
Flexible status and transition system.
"""

# mypy: disable-error-code="assignment,misc,override"

import uuid

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class StatusDefinitionBase(Base):
    """Status catalog by entity type (flexible, extensible)"""

    entity: str = Field(
        max_length=50,
        index=True,
        description="Entity type: route, consolidation, delivery_task",
    )
    code: str = Field(
        max_length=50,
        index=True,
        description="Status code: draft, ready, dispatched, in_transit, arrived, closed",
    )
    name: str = Field(max_length=100, description="Display name of status")
    description: str | None = Field(
        default=None, max_length=500, description="Status description"
    )
    sequence_order: int = Field(default=0, description="Display order")
    is_terminal: bool = Field(
        default=False, description="Terminal status (end of process)"
    )
    is_error: bool = Field(
        default=False, description="Indicates an error or exception state"
    )

    # UI customization
    ui_color: str | None = Field(
        default=None, max_length=20, description="Color for interface"
    )
    ui_icon: str | None = Field(
        default=None, max_length=50, description="Icon for interface"
    )


class StatusDefinition(StatusDefinitionBase, table=True):
    """Status catalog by entity type (flexible, extensible)"""

    __tablename__ = "status_definitions"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True),
    )


class StatusDefinitionCreate(StatusDefinitionBase, BaseCreate):
    """Represents status definition create."""

    pass


class StatusDefinitionUpdate(StatusDefinitionBase, BaseUpdate):
    """Represents status definition update."""

    entity: str | None = None  # type: ignore[assignment]
    code: str | None = None  # type: ignore[assignment]
    name: str | None = None  # type: ignore[assignment]
    description: str | None = None
    rank: int | None = None
    is_terminal: bool | None = None  # type: ignore[assignment]
    is_error: bool | None = None  # type: ignore[assignment]
    ui_color: str | None = None
    ui_icon: str | None = None


class StatusDefinitionPublic(StatusDefinitionBase, BasePublic):
    """Represents status definition public."""

    id: uuid.UUID


class StatusTransitionBase(Base):
    """Allowed transitions between statuses (guards are coded in service)"""

    entity: str = Field(max_length=50, index=True, description="Entity type")
    from_code: str = Field(max_length=50, description="Source status")
    to_code: str = Field(max_length=50, description="Target status")
    guard_name: str | None = Field(
        default=None, max_length=100, description="Business guard name"
    )
    auto_advance: bool = Field(default=False, description="Automatic transition")

    # Conditions
    requires_confirmation: bool = Field(
        default=False, description="Requires confirmation"
    )
    requires_scan: bool = Field(default=False, description="Requires scan")


class StatusTransition(StatusTransitionBase, table=True):
    """Allowed transitions between statuses"""

    __tablename__ = "status_transitions"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True),
    )


class StatusTransitionCreate(StatusTransitionBase, BaseCreate):
    """Represents status transition create."""

    pass


class StatusTransitionUpdate(StatusTransitionBase, BaseUpdate):
    """Represents status transition update."""

    entity: str | None = None  # type: ignore[assignment]
    from_code: str | None = None  # type: ignore[assignment]
    to_code: str | None = None  # type: ignore[assignment]
    guard_name: str | None = None
    auto_advance: bool | None = None  # type: ignore[assignment]
    requires_confirmation: bool | None = None  # type: ignore[assignment]
    requires_scan: bool | None = None  # type: ignore[assignment]


class StatusTransitionPublic(StatusTransitionBase, BasePublic):
    """Represents status transition public."""

    id: uuid.UUID


class StatusDefinitionsPublic(SQLModel):
    """Represents status definitions public."""

    data: list[StatusDefinitionPublic] = Field(
        default_factory=list,
        description="List of status definitions",
    )
    count: int = Field(
        default=0,
        description="Total number of status definitions",
    )


class StatusTransitionsPublic(SQLModel):
    """Represents status transitions public."""

    data: list[StatusTransitionPublic] = Field(
        default_factory=list,
        description="List of status transitions",
    )
    count: int = Field(
        default=0,
        description="Total number of status transitions",
    )
