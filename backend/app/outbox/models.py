from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional
from sqlmodel import SQLModel, Field, Column, JSON, String
from uuid import UUID, uuid4

OutboxStatus = Literal["PENDING", "RUNNING", "DONE", "FAILED"]

class OutboxEvent(SQLModel, table=True):
    __tablename__ = "outbox_event"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    type: str = Field(index=True)                 # ex: "CREATE_PAYMENT"
    payload: Dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    status: OutboxStatus = Field(
        default="PENDING", 
        sa_column=Column(String, nullable=False, index=True)
    )
    attempts: int = 0
    next_run_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    last_error: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def touch(self):
        self.updated_at = datetime.now(timezone.utc)