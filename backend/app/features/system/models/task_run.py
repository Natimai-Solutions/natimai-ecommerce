"""Journal of the background tasks: when each one last ran, succeeded, failed.

Twelve scheduled tasks ran with nothing to say whether they still did: the
price and stock sync returned « success » with errors, the nightly price
refresh only logged its failure (functional audit, November 2026). One row
per task (per supplier for the supplier tasks), updated at every run.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Column, DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def _now() -> datetime:
    return datetime.now(UTC)


class TaskRun(SQLModel, table=True):
    """The last runs of one background task."""

    __tablename__ = "task_runs"

    #: Task name, with the supplier for the supplier tasks (``inventory:ingram``).
    name: str = Field(primary_key=True, max_length=150)
    last_started_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    last_finished_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    last_success_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    last_failure_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    #: ok | partial (finished, with errors) | failed
    last_status: str | None = Field(default=None, max_length=16)
    last_error: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    last_result: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSONB, nullable=True)
    )
    runs: int = Field(default=0)
    failures: int = Field(default=0)
    consecutive_failures: int = Field(default=0)
    last_alert_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    updated_at: datetime = Field(
        default_factory=_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, default=_now),
    )
