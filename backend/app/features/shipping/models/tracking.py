"""
ModÃ¨les de suivi et Ã©vÃ©nements.
Journal de tous les changements et suivi par Ã©tapes.
"""

import uuid
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from datetime import datetime

from sqlmodel import Field, Relationship, SQLModel, Column, JSON
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class TrackingEventBase(SQLModel):
    """Journal inviolable de tous les changements pour audit & timeline"""
    
    # Sujet de l'Ã©vÃ©nement (polymorphe)
    subject_type: str = Field(max_length=50, description="Type d'entitÃ©: route, step, consolidation, order_step")
    subject_id: uuid.UUID = Field(description="ID de l'entitÃ© concernÃ©e")
    
    # Changement de statut
    status_from: Optional[str] = Field(default=None, max_length=50, description="Statut prÃ©cÃ©dent")
    status_to: str = Field(max_length=50, description="Nouveau statut")
    
    # Timing
    occurred_at: datetime = Field(description="Quand l'Ã©vÃ©nement s'est produit")
    recorded_at: datetime = Field(default_factory=datetime.utcnow, description="Quand il a Ã©tÃ© enregistrÃ©")
    
    # Contexte
    scan_ref: Optional[str] = Field(default=None, max_length=100, description="RÃ©fÃ©rence de scan/code-barres")
    location: Optional[str] = Field(default=None, max_length=200, description="Lieu de l'Ã©vÃ©nement")
    actor: Optional[str] = Field(default=None, max_length=100, description="Qui a dÃ©clenchÃ© l'Ã©vÃ©nement")
    
    # Description
    event_type: str = Field(max_length=50, description="Type d'Ã©vÃ©nement: scan, update, exception")
    description: Optional[str] = Field(default=None, max_length=500, description="Description libre")
    
    # MÃ©tadonnÃ©es flexibles
    event_metadata: Optional[str] = Field(default=None, sa_column=Column(JSON), description="DonnÃ©es supplÃ©mentaires")
    
    # Preuve / Evidence
    evidence_url: Optional[str] = Field(default=None, max_length=500, description="URL de preuve (photo, signature)")
    signature_name: Optional[str] = Field(default=None, max_length=100, description="Nom du signataire")


class TrackingEvent(TrackingEventBase, table=True):
    """Journal inviolable de tous les changements pour audit & timeline"""
    __tablename__ = "tracking_events"
    
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True)
    )


class TrackingEventCreate(TrackingEventBase):
    pass


class TrackingEventUpdate(SQLModel):
    # Les Ã©vÃ©nements de tracking ne doivent normalement pas Ãªtre modifiÃ©s
    # Seule la description ou les mÃ©tadonnÃ©es peuvent Ãªtre enrichies
    description: Optional[str] = None
    event_metadata: Optional[str] = None
    evidence_url: Optional[str] = None


class TrackingEventPublic(TrackingEventBase):
    id: uuid.UUID



class TrackingEventsPublic(SQLModel):
    data: list[TrackingEventPublic] = Field(
        default_factory=list,
        description="List of tracking events",
    )
    count: int = Field(
        default=0,
        description="Total number of tracking events",
    )


