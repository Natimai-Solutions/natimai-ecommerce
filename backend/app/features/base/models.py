import datetime
import uuid

from sqlmodel import Field, SQLModel


class BaseCreate(SQLModel):
    """Represents base create."""

    is_active: bool = Field(default=True)


class BaseUpdate(SQLModel):
    """Represents base update."""

    is_active: bool | None = None


class Base(SQLModel):
    """Represents base."""

    is_active: bool = Field(default=True)
    is_admin_active: bool = Field(default=True)
    created_at: datetime.datetime | None = Field(default=None)
    created_by_id: uuid.UUID | None = Field(
        default=None, foreign_key="users.id", nullable=True
    )
    modify_at: datetime.datetime | None = Field(default=None)
    modify_by_id: uuid.UUID | None = Field(
        default=None, foreign_key="users.id", nullable=True
    )


class BasePublic(SQLModel):
    """Represents base public."""

    is_active: bool
    created_at: datetime.datetime | None
    created_by_id: uuid.UUID | None
    modify_at: datetime.datetime | None = Field(default_factory=datetime.datetime.now)
    modify_by_id: uuid.UUID | None = None


# Generic message
class Message(SQLModel):
    """Represents message."""

    id: uuid.UUID | None = None
    message: str
    task_id: uuid.UUID | None = None
