import uuid
from datetime import datetime

from pydantic import field_validator
from sqlmodel import Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


def validate_notification_type(v: str) -> str:
    """Validate that notification type is one of the allowed values."""
    allowed_types = {
        "order_confirmation",
        "order_status_update",
        "payment_success",
        "payment_failed",
        "shipping_started",
        "shipping_delivered",
        "product_available",
        "product_low_stock",
        "account_verification",
        "password_reset",
        "promotional_offer",
        "system_maintenance",
    }
    if v not in allowed_types:
        raise ValueError(f"Type must be one of: {', '.join(allowed_types)}")
    return v


def validate_priority(v: int) -> int:
    """Validate that priority is between 1 and 4."""
    if v < 1 or v > 4:
        raise ValueError("Priority must be between 1 (low) and 4 (high)")
    return v


class NotificationBase(Base):
    title: str = Field(description="Title of the notification", max_length=255)
    content: str = Field(description="Content of the notification", max_length=1000)
    type: str = Field(description="Type of notification")
    priority: int = Field(
        default=1, description="Priority level from 1 (low) to 4 (high)"
    )
    order_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="orders.id",
        description="Related order ID",
        index=True,
    )
    product_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="products.id",
        description="Related product ID",
        index=True,
    )
    payment_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="payments.id",
        description="Related payment ID",
        index=True,
    )
    action_url: str | None = Field(
        default=None, description="Action URL for the notification", max_length=500
    )
    action_label: str | None = Field(
        default=None, description="Action button label", max_length=100
    )

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        """Validate that type is one of the allowed values."""
        return validate_notification_type(v)

    @field_validator("priority")
    @classmethod
    def validate_priority_field(cls, v: int) -> int:
        """Validate that priority is between 1 and 4."""
        return validate_priority(v)


class NotificationCreate(NotificationBase, BaseCreate):
    pass


class NotificationUpdate(NotificationBase, BaseUpdate):
    title: str | None = None
    content: str | None = None
    type: str | None = None
    priority: int | None = None
    order_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None
    payment_id: uuid.UUID | None = None
    action_url: str | None = None
    action_label: str | None = None


class Notification(NotificationBase, table=True):
    __tablename__ = "notifications"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)


class NotificationPublic(NotificationBase, BasePublic):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)


class NotificationsPublic(SQLModel):
    data: list[NotificationPublic] = Field(
        default_factory=list, description="List of notifications"
    )
    count: int = Field(default=0, description="Total number of notifications")


# User Notification Link models for many-to-many relationship
class UserNotificationBase(Base):
    is_read: bool = Field(
        default=False, description="Whether the notification has been read"
    )
    read_at: datetime | None = Field(
        default=None, description="When the notification was read"
    )
    sent_at: datetime = Field(
        default_factory=datetime.now, description="When the notification was sent"
    )


class UserNotificationCreate(UserNotificationBase, BaseCreate):
    notification_id: uuid.UUID = Field(description="ID of the notification")
    user_id: uuid.UUID = Field(description="ID of the user")


class UserNotificationUpdate(UserNotificationBase, BaseUpdate):
    is_read: bool | None = None
    read_at: datetime | None = None


class UserNotification(UserNotificationBase, Base, table=True):
    __tablename__ = "user_notifications"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    notification_id: uuid.UUID = Field(
        foreign_key="notifications.id",
        nullable=False,
        index=True,
        description="ID of the notification",
    )
    user_id: uuid.UUID = Field(
        foreign_key="users.id", nullable=False, index=True, description="ID of the user"
    )


class UserNotificationPublic(UserNotificationBase, BasePublic):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    notification_id: uuid.UUID = Field(description="ID of the notification")
    user_id: uuid.UUID = Field(description="ID of the user")


class UserNotificationsPublic(SQLModel):
    data: list[UserNotificationPublic] = Field(
        default_factory=list, description="List of user notifications"
    )
    count: int = Field(default=0, description="Total number of user notifications")
