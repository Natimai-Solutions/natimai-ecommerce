import datetime
import enum
import uuid

from sqlmodel import Field, Relationship, SQLModel

from app.features.base.models import Base, BaseCreate, BaseUpdate, BasePublic
from app.features.user.models.user import User


class NotificationType(enum.Enum):
    ORDER_CONFIRMATION = "order_confirmation"
    ORDER_STATUS_UPDATE = "order_status_update"
    PAYMENT_SUCCESS = "payment_success"
    PAYMENT_FAILED = "payment_failed"
    SHIPPING_STARTED = "shipping_started"
    SHIPPING_DELIVERED = "shipping_delivered"
    PRODUCT_AVAILABLE = "product_available"
    PRODUCT_LOW_STOCK = "product_low_stock"
    ACCOUNT_VERIFICATION = "account_verification"
    PASSWORD_RESET = "password_reset"
    PROMOTIONAL_OFFER = "promotional_offer"
    SYSTEM_MAINTENANCE = "system_maintenance"


class EmailFrequency(enum.Enum):
    IMMEDIATE = "immediate"
    DAILY = "daily"
    WEEKLY = "weekly"
    NEVER = "never"


class NotificationUserLink(SQLModel, table=True):
    __tablename__ = "notification_user_links"
    notification_id: uuid.UUID = Field(
        foreign_key="notifications.id", primary_key=True, ondelete="CASCADE"
    )
    user_id: uuid.UUID = Field(
        foreign_key="users.id", primary_key=True, ondelete="CASCADE"
    )

    is_read: bool = Field(default=False)
    read_at: datetime.datetime | None = Field(default=None)
    sent_at: datetime.datetime = Field(default_factory=datetime.datetime.now)


class NotificationBase(Base):
    title: str | None = Field(default=None, max_length=255, description="Title of the notification")
    content: str | None = Field(default=None, max_length=1000, description="Content of the notification")
    type: NotificationType = Field(default=NotificationType.SYSTEM_MAINTENANCE, description="Type of notification")
    priority: int = Field(default=1, ge=1, le=4, description="Priority level from 1 (low) to 4 (high)")
    order_id: uuid.UUID | None = Field(default=None, foreign_key="orders.id", description="Related order ID")
    product_id: uuid.UUID | None = Field(default=None, foreign_key="products.id", description="Related product ID")
    payment_id: uuid.UUID | None = Field(default=None, foreign_key="payments.id", description="Related payment ID")
    action_url: str | None = Field(default=None, max_length=500, description="Action URL for the notification")
    action_label: str | None = Field(default=None, max_length=100, description="Action button label")


class NotificationCreate(NotificationBase, BaseCreate):
    title: str = Field(..., max_length=255, description="Title of the notification")
    content: str = Field(..., max_length=1000, description="Content of the notification")


class NotificationCreateWithRecipients(NotificationCreate):
    user_ids: list[uuid.UUID] = Field(..., min_items=1, description="List of recipient user IDs")


class NotificationUpdate(NotificationBase, BaseUpdate):
    pass


class NotificationUpdateWithRecipients(NotificationUpdate):
    user_ids: list[uuid.UUID] | None = None


class Notification(NotificationBase, Base, table=True):
    __tablename__ = "notifications"
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        description="Unique identifier for the notification"
    )

    recipients: list[User] = Relationship(
        link_model=NotificationUserLink, sa_relationship_kwargs={"lazy": "selectin"}
    )


class NotificationPublic(NotificationBase, BasePublic):
    id: uuid.UUID = Field(..., description="Unique identifier for the notification")
    is_read: bool | None = Field(default=None, description="Whether the notification has been read")
    read_at: datetime.datetime | None = Field(default=None, description="When the notification was read")


class NotificationsPublic(SQLModel):
    data: list[NotificationPublic] = Field(
        default_factory=list, description="List of notifications"
    )
    count: int = Field(default=0, description="Total number of notifications")


class NotificationRestricted(NotificationBase, BasePublic):
    id: uuid.UUID = Field(..., description="Unique identifier for the notification")
    recipients: list[User] | None = Field(default=None, description="List of notification recipients")


class NotificationsRestricted(SQLModel):
    data: list[NotificationRestricted] = Field(
        default_factory=list, description="List of notifications with recipients"
    )
    count: int = Field(default=0, description="Total number of notifications")


class NotificationStats(SQLModel):
    total_recipients: int = Field(..., description="Total number of recipients")
    read_by: int = Field(..., description="Number of recipients who read the notification")
    read_percentage: float = Field(..., description="Percentage of recipients who read the notification")
    delivery_rate: float | None = Field(default=None, description="Delivery success rate")
    click_through_rate: float | None = Field(default=None, description="Click-through rate for action URLs")
