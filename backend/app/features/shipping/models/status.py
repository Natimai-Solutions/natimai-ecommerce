"""
Modèles de statuts configurables.
Système flexible de statuts et transitions.
"""

import uuid
from typing import Optional

from sqlmodel import Field, SQLModel
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class StatusDefinitionBase(Base):
    """Catalogue de statuts par type d'entité (souple, extensible)"""
    entity: str = Field(max_length=50, description="Type d'entité: route, step, consolidation, delivery_task, order_step")
    code: str = Field(max_length=50, description="Code du statut: draft, ready, dispatched, in_transit, arrived, closed")
    name: str = Field(max_length=100, description="Nom affichable du statut")
    description: Optional[str] = Field(default=None, max_length=500, description="Description du statut")
    rank: int = Field(default=0, description="Ordre d'affichage")
    is_terminal: bool = Field(default=False, description="Statut terminal (fin de processus)")
    
    # Personnalisation UI
    ui_color: Optional[str] = Field(default=None, max_length=20, description="Couleur pour l'interface")
    ui_icon: Optional[str] = Field(default=None, max_length=50, description="Icône pour l'interface")


class StatusDefinition(StatusDefinitionBase, table=True):
    """Catalogue de statuts par type d'entité (souple, extensible)"""
    __tablename__ = "status_definitions"
    
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True)
    )


class StatusDefinitionCreate(StatusDefinitionBase, BaseCreate):
    pass


class StatusDefinitionUpdate(StatusDefinitionBase, BaseUpdate):
    entity: Optional[str] = None
    code: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    rank: Optional[int] = None
    is_terminal: Optional[bool] = None
    ui_color: Optional[str] = None
    ui_icon: Optional[str] = None


class StatusDefinitionPublic(StatusDefinitionBase, BasePublic):
    id: uuid.UUID


class StatusTransitionBase(Base):
    """Transitions autorisées entre statuts (les gardes sont codées côté service)"""
    entity: str = Field(max_length=50, description="Type d'entité")
    from_code: str = Field(max_length=50, description="Statut de départ")
    to_code: str = Field(max_length=50, description="Statut d'arrivée")
    guard_name: Optional[str] = Field(default=None, max_length=100, description="Nom de la garde métier")
    auto_advance: bool = Field(default=False, description="Transition automatique")
    
    # Conditions
    requires_confirmation: bool = Field(default=False, description="Nécessite une confirmation")
    requires_scan: bool = Field(default=False, description="Nécessite un scan")


class StatusTransition(StatusTransitionBase, table=True):
    """Transitions autorisées entre statuts"""
    __tablename__ = "status_transitions"
    
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True)
    )


class StatusTransitionCreate(StatusTransitionBase, BaseCreate):
    pass


class StatusTransitionUpdate(StatusTransitionBase, BaseUpdate):
    entity: Optional[str] = None
    from_code: Optional[str] = None
    to_code: Optional[str] = None
    guard_name: Optional[str] = None
    auto_advance: Optional[bool] = None
    requires_confirmation: Optional[bool] = None
    requires_scan: Optional[bool] = None


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