import datetime
import uuid

from sqlmodel import Field, SQLModel


class BaseCreate(SQLModel):
    is_active: bool = Field(default=True)


class BaseUpdate(SQLModel):
    is_active: bool | None = None


class Base(SQLModel):
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
    is_active: bool
    created_at: datetime.datetime | None
    created_by_id: uuid.UUID | None
    modify_at: datetime.datetime | None = Field(default_factory=datetime.datetime.now)
    modify_by_id: uuid.UUID | None = None


# Generic message
class Message(SQLModel):
    id: uuid.UUID | None = None
    message: str
    task_id: uuid.UUID | None = None
