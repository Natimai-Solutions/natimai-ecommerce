import uuid
from typing import Optional

from sqlmodel import and_, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase, track_crud_operation
from app.features.user.models.notification import (
    Notification,
    NotificationCreate,
    NotificationCreateWithRecipients,
    NotificationUpdate,
    NotificationUserLink,
    NotificationStats,
    NotificationType,
)


class NotificationCrud(
    CrudBase[Notification, NotificationCreate, NotificationUpdate]
):
    
    async def create_with_recipients(
        self,
        session: AsyncSession,
        *,
        obj_in: NotificationCreateWithRecipients,
        current_user: Optional[uuid.UUID] = None,
    ) -> Notification:
        notification_data = obj_in.model_dump(exclude={"user_ids"})
        notification_data["created_by_id"] = current_user
        db_notification = Notification(**notification_data)
        
        session.add(db_notification)
        await session.commit()
        await session.refresh(db_notification)
        
        for user_id in obj_in.user_ids:
            link = NotificationUserLink(
                notification_id=db_notification.id,
                user_id=user_id
            )
            session.add(link)
        
        await session.commit()
        await session.refresh(db_notification)
        return db_notification

    async def get_user_notifications(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
        unread_only: bool = False,
        notification_type: Optional[NotificationType] = None,
    ) -> list[Notification]:
        statement = (
            select(Notification)
            .join(NotificationUserLink)
            .where(NotificationUserLink.user_id == user_id)
            .where(Notification.is_active.is_(True))
        )
        
        if unread_only:
            statement = statement.where(NotificationUserLink.is_read.is_(False))
            
        if notification_type:
            statement = statement.where(Notification.type == notification_type)
            
        statement = (
            statement
            .order_by(NotificationUserLink.sent_at.desc())
            .offset(skip)
            .limit(limit)
        )
        
        result = await session.exec(statement)
        return result.all()

    async def mark_as_read(
        self,
        session: AsyncSession,
        *,
        notification_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        statement = select(NotificationUserLink).where(
            and_(
                NotificationUserLink.notification_id == notification_id,
                NotificationUserLink.user_id == user_id,
            )
        )
        
        result = await session.exec(statement)
        link = result.first()
        
        if not link:
            return False
            
        link.is_read = True
        link.read_at = func.now()
        
        session.add(link)
        await session.commit()
        return True

    async def mark_all_as_read(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
    ) -> int:
        statement = select(NotificationUserLink).where(
            and_(
                NotificationUserLink.user_id == user_id,
                NotificationUserLink.is_read.is_(False),
            )
        )
        
        result = await session.exec(statement)
        links = result.all()
        
        count = 0
        for link in links:
            link.is_read = True
            link.read_at = func.now()
            session.add(link)
            count += 1
            
        await session.commit()
        return count

    async def get_unread_count(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
    ) -> int:
        statement = select(func.count(NotificationUserLink.notification_id)).where(
            and_(
                NotificationUserLink.user_id == user_id,
                NotificationUserLink.is_read.is_(False),
            )
        )
        
        result = await session.exec(statement)
        return result.one()

    async def get_notification_stats(
        self,
        session: AsyncSession,
        *,
        notification_id: uuid.UUID,
    ) -> Optional[NotificationStats]:
        total_statement = select(func.count(NotificationUserLink.notification_id)).where(
            NotificationUserLink.notification_id == notification_id
        )
        total_result = await session.exec(total_statement)
        total_recipients = total_result.one()
        
        if total_recipients == 0:
            return None
        
        read_statement = select(func.count(NotificationUserLink.notification_id)).where(
            and_(
                NotificationUserLink.notification_id == notification_id,
                NotificationUserLink.is_read.is_(True),
            )
        )
        read_result = await session.exec(read_statement)
        read_by = read_result.one()
        
        read_percentage = (read_by / total_recipients) * 100 if total_recipients > 0 else 0
        
        return NotificationStats(
            total_recipients=total_recipients,
            read_by=read_by,
            read_percentage=round(read_percentage, 2),
        )

    async def get_notifications_by_type(
        self,
        session: AsyncSession,
        *,
        notification_type: NotificationType,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Notification]:
        statement = (
            select(Notification)
            .where(
                and_(
                    Notification.type == notification_type,
                    Notification.is_active.is_(True),
                )
            )
            .order_by(Notification.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        
        result = await session.exec(statement)
        return result.all()

    async def delete_old_notifications(
        self,
        session: AsyncSession,
        *,
        days_old: int = 90,
    ) -> int:
        cutoff_date = func.now() - func.interval(f"{days_old} days")
        
        statement = (
            select(Notification)
            .where(
                and_(
                    Notification.created_at < cutoff_date,
                    Notification.is_active.is_(True),
                )
            )
        )
        
        result = await session.exec(statement)
        notifications = result.all()
        
        count = 0
        for notification in notifications:
            notification.is_active = False
            session.add(notification)
            count += 1
            
        await session.commit()
        return count


crud_notification = NotificationCrud(
    model=Notification,
    schema_create=NotificationCreate,
    schema_update=NotificationUpdate,
    order_by=Notification.created_at,
)