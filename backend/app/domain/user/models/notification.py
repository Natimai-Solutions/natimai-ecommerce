import uuid
from enum import Enum

from sqlmodel import Field, SQLModel

from app.api.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class NotificationType(str, Enum):
	ORDER = "ORDER"
	PROMO = "PROMO"
	SYSTEM = "SYSTEM"


class NotificationBase(SQLModel):
	title: str = Field(description="Notification title", max_length=255)
	content: str = Field(description="Notification content")
	type: NotificationType = Field(default=NotificationType.SYSTEM)
	is_read: bool = Field(default=False)
	user_id: uuid.UUID = Field(foreign_key="users.id")


class NotificationCreate(NotificationBase, BaseCreate):
	pass


class NotificationUpdate(BaseUpdate):
	title: str | None = None
	content: str | None = None
	type: NotificationType | None = None
	is_read: bool | None = None


class Notification(NotificationBase, Base, table=True):
	__tablename__ = "notifications"
	id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)


class NotificationPublic(NotificationBase, BasePublic):
	id: uuid.UUID


class NotificationsPublic(SQLModel):
	data: list[NotificationPublic] = Field(default_factory=list)
	count: int = Field(default=0)
