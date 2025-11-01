import uuid

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.user.models.notification import (
    Notification,
    NotificationCreate,
    NotificationUpdate,
    UserNotification,
    UserNotificationCreate,
    UserNotificationUpdate,
)


class NotificationCrud(CrudBase[Notification, NotificationCreate, NotificationUpdate]):
    async def get_by_user_id(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
        unread_only: bool = False,
    ) -> list[Notification]:
        """Get notifications for a specific user."""
        statement = (
            select(Notification)
            .join(UserNotification, Notification.id == UserNotification.notification_id)
            .where(
                UserNotification.user_id == user_id,
                Notification.is_admin_active.is_(True),
                Notification.is_active.is_(True),
            )
        )

        if unread_only:
            statement = statement.where(UserNotification.is_read.is_(False))

        statement = (
            statement.offset(skip)
            .limit(limit)
            .order_by(UserNotification.sent_at.desc())
        )

        exec_result = await session.exec(statement)
        return exec_result.all()

    async def get_user_notification(
        self, session: AsyncSession, *, notification_id: uuid.UUID, user_id: uuid.UUID
    ) -> Notification | None:
        """Get a specific notification for a user."""
        statement = (
            select(Notification)
            .join(UserNotification, Notification.id == UserNotification.notification_id)
            .where(
                Notification.id == notification_id,
                UserNotification.user_id == user_id,
                Notification.is_admin_active.is_(True),
                Notification.is_active.is_(True),
            )
        )
        exec_result = await session.exec(statement)
        return exec_result.first()

    async def create_for_users(
        self,
        session: AsyncSession,
        *,
        data: NotificationCreate,
        user_ids: list[uuid.UUID],
        current_user: uuid.UUID | None = None,
    ) -> Notification:
        """Create a notification and assign it to multiple users."""
        # Create the notification
        obj_data = data.model_dump()
        if current_user:
            obj_data["created_by_id"] = current_user
        record = self.model(**obj_data)
        session.add(record)
        await session.commit()
        await session.refresh(record)

        # Create user notification links
        for user_id in user_ids:
            user_notification = UserNotification(
                notification_id=record.id, user_id=user_id
            )
            session.add(user_notification)

        await session.commit()
        await session.refresh(record)
        return record

    async def count_by_user(
        self, session: AsyncSession, *, user_id: uuid.UUID, unread_only: bool = False
    ) -> int:
        """Count notifications for a user."""
        statement = (
            select(Notification)
            .join(UserNotification, Notification.id == UserNotification.notification_id)
            .where(
                UserNotification.user_id == user_id,
                Notification.is_admin_active.is_(True),
                Notification.is_active.is_(True),
            )
        )

        if unread_only:
            statement = statement.where(UserNotification.is_read.is_(False))

        exec_result = await session.exec(statement)
        return len(exec_result.all())


class UserNotificationCrud(
    CrudBase[UserNotification, UserNotificationCreate, UserNotificationUpdate]
):
    async def mark_as_read(
        self, session: AsyncSession, *, notification_id: uuid.UUID, user_id: uuid.UUID
    ) -> UserNotification | None:
        """Mark a notification as read for a specific user."""
        statement = select(self.model).where(
            self.model.notification_id == notification_id,
            self.model.user_id == user_id,
            self.model.is_admin_active.is_(True),
            self.model.is_active.is_(True),
        )
        exec_result = await session.exec(statement)
        user_notification = exec_result.first()

        if not user_notification:
            return None

        user_notification.is_read = True
        from datetime import datetime

        user_notification.read_at = datetime.now()

        session.add(user_notification)
        await session.commit()
        await session.refresh(user_notification)
        return user_notification

    async def mark_all_as_read(
        self, session: AsyncSession, *, user_id: uuid.UUID
    ) -> int:
        """Mark all notifications as read for a user."""
        statement = select(self.model).where(
            self.model.user_id == user_id,
            self.model.is_read.is_(False),
            self.model.is_admin_active.is_(True),
            self.model.is_active.is_(True),
        )
        exec_result = await session.exec(statement)
        user_notifications = exec_result.all()

        count = 0
        from datetime import datetime

        for user_notification in user_notifications:
            user_notification.is_read = True
            user_notification.read_at = datetime.now()
            session.add(user_notification)
            count += 1

        await session.commit()
        return count


crud_notification = NotificationCrud(
    model=Notification,
    schema_create=NotificationCreate,
    schema_update=NotificationUpdate,
    order_by=Notification.created_at,
)

crud_user_notification = UserNotificationCrud(
    model=UserNotification,
    schema_create=UserNotificationCreate,
    schema_update=UserNotificationUpdate,
    order_by=UserNotification.sent_at,
)
