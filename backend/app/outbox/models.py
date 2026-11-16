from datetime import UTC, datetime
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
    next_run_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    last_error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def touch(self) -> None:
        """Execute touch."""
        self.updated_at = datetime.now(UTC)


class OutboxHandlerFailure(SQLModel, table=True):
    """A handler given up on an event after all its retries.

    The event itself is ``DONE`` (it was handed to the workers): without this
    row, an abandoned delivery — an invoice not issued, a payment status not
    synced — left only a log line and an alert (functional audit, November
    2026). The back office lists them and replays them.
    """

    __tablename__ = "outbox_handler_failures"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    event_id: UUID = Field(index=True)
    event_type: str = Field(index=True)
    handler_path: str
    payload: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    error: str | None = None
    tries: int = 0
    failed_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    #: Set when replayed (or dismissed) from the back office.
    resolved_at: datetime | None = None
    resolution: str | None = None
