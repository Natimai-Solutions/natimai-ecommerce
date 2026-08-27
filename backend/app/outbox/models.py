from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID, uuid4

from sqlmodel import JSON, Column, Field, SQLModel, String

OutboxStatus = Literal["PENDING", "RUNNING", "DONE", "FAILED"]


class OutboxEvent(SQLModel, table=True):
    """Represents outbox event."""

    __tablename__ = "outbox_event"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    type: str = Field(index=True)  # ex: "CREATE_PAYMENT"
    correlation_id: UUID | None = Field(default=None, index=True)
    payload: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    status: OutboxStatus = Field(
        default="PENDING", sa_column=Column(String, nullable=False, index=True)
    )
    attempts: int = 0
    next_run_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), index=True
    )
    last_error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def touch(self) -> None:
        """Execute touch."""
        self.updated_at = datetime.now(timezone.utc)
