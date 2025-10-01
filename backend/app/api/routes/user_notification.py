import uuid

from fastapi import HTTPException, Query, status
from app.api.base_router import BaseRouter
from app.api.deps import CurrentUser, SessionDep
from app.features.user.crud.notification import (
    NotificationCrud,
    crud_notification,
    crud_user_notification,
)
from app.features.user.models.notification import (
    Notification,
    NotificationCreate,
    NotificationPublic,
    NotificationsPublic,
    NotificationUpdate,
)


def _check_permission(
    current_user_id: uuid.UUID, user_id: uuid.UUID, is_admin: bool = False
) -> bool:
    """Check if current user can access resource for given user_id."""
    return current_user_id == user_id or is_admin


class NotificationRouter(
    BaseRouter[
        Notification,
        NotificationCreate,
        NotificationUpdate,
        NotificationPublic,
        NotificationsPublic,
        NotificationCrud,
    ]
):
    pass


class Auth:
    read = True
    create = True
    update = True
    delete = True


router = NotificationRouter(
    name="notification",
    tags=["notification"],
    crud=crud_notification,
    schema_public=NotificationPublic,
    schema_publics=NotificationsPublic,
    schema_create=NotificationCreate,
    schema_update=NotificationUpdate,
    auth=Auth(),
    auto=True,
)


# User-specific notification routes
@router.get("/users/{user_id}/notifications", response_model=NotificationsPublic)
async def get_user_notifications(
    session: SessionDep,
    current_user: CurrentUser,
    user_id: uuid.UUID,
    skip: int = Query(default=0, ge=0, description="Number of notifications to skip"),
    limit: int = Query(default=100, le=100, ge=1, description="Number of notifications to return"),
    unread_only: bool = False,
) -> NotificationsPublic:
    """Get all notifications for a specific user."""
    if not _check_permission(current_user.id, user_id, current_user.is_superuser):
        raise HTTPException(status_code=403, detail="Not authorized")

    notifications = await crud_notification.get_by_user_id(
        session=session,
        user_id=user_id,
        skip=skip,
        limit=limit,
        unread_only=unread_only,
    )
    count = await crud_notification.count_by_user(
        session=session, user_id=user_id, unread_only=False
    )
    return NotificationsPublic(data=notifications, count=count)


@router.get("/users/{user_id}/notifications/unread/count")
async def get_user_unread_notifications_count(
    session: SessionDep,
    current_user: CurrentUser,
    user_id: uuid.UUID,
) -> dict:
    """Get count of unread notifications for a specific user."""
    if not _check_permission(current_user.id, user_id, current_user.is_superuser):
        raise HTTPException(status_code=403, detail="Not authorized")

    count = await crud_notification.count_by_user(
        session=session, user_id=user_id, unread_only=True
    )
    return {"user_id": user_id, "unread_count": count}


@router.get("/users/{user_id}/notifications/{notification_id}", response_model=NotificationPublic)
async def get_user_notification(
    session: SessionDep,
    current_user: CurrentUser,
    user_id: uuid.UUID,
    notification_id: uuid.UUID,
) -> NotificationPublic:
    """Get a specific notification for a user."""
    if not _check_permission(current_user.id, user_id, current_user.is_superuser):
        raise HTTPException(status_code=403, detail="Not authorized")

    user_notification = await crud_user_notification.get_by_user_and_notification(
        session=session, user_id=user_id, notification_id=notification_id
    )
    if not user_notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    notification = await crud_notification.get(session=session, id=notification_id)
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    return NotificationPublic.model_validate(notification)


@router.patch("/users/{user_id}/notifications/{notification_id}/read")
async def mark_notification_as_read(
    session: SessionDep,
    current_user: CurrentUser,
    user_id: uuid.UUID,
    notification_id: uuid.UUID,
) -> dict:
    """Mark a notification as read for a specific user."""
    if not _check_permission(current_user.id, user_id, current_user.is_superuser):
        raise HTTPException(status_code=403, detail="Not authorized")

    user_notification = await crud_user_notification.get_by_user_and_notification(
        session=session, user_id=user_id, notification_id=notification_id
    )
    if not user_notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    if user_notification.is_read:
        return {"message": "Notification already marked as read"}

    await crud_user_notification.mark_as_read(
        session=session, user_id=user_id, notification_id=notification_id
    )
    return {"message": "Notification marked as read"}


@router.patch("/users/{user_id}/notifications/mark-all-read")
async def mark_all_notifications_as_read(
    session: SessionDep,
    current_user: CurrentUser,
    user_id: uuid.UUID,
) -> dict:
    """Mark all notifications as read for a specific user."""
    if not _check_permission(current_user.id, user_id, current_user.is_superuser):
        raise HTTPException(status_code=403, detail="Not authorized")

    count = await crud_user_notification.mark_all_as_read(
        session=session, user_id=user_id
    )
    return {"message": f"Marked {count} notifications as read"}


@router.delete("/users/{user_id}/notifications/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_notification(
    session: SessionDep,
    current_user: CurrentUser,
    user_id: uuid.UUID,
    notification_id: uuid.UUID,
) -> None:
    """Delete a notification for a specific user."""
    if not _check_permission(current_user.id, user_id, current_user.is_superuser):
        raise HTTPException(status_code=403, detail="Not authorized")

    user_notification = await crud_user_notification.get_by_user_and_notification(
        session=session, user_id=user_id, notification_id=notification_id
    )
    if not user_notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    await crud_user_notification.remove(session=session, id=user_notification.id)


@router.post("/users/{user_id}/notifications", response_model=NotificationPublic, status_code=status.HTTP_201_CREATED)
async def create_user_notification(
    session: SessionDep,
    current_user: CurrentUser,
    user_id: uuid.UUID,
    notification_in: NotificationCreate,
) -> NotificationPublic:
    """Create a new notification for a user."""
    if not _check_permission(current_user.id, user_id, current_user.is_superuser):
        raise HTTPException(status_code=403, detail="Not authorized")

    # Create the notification
    notification = await crud_notification.create(
        session=session, obj_in=notification_in
    )

    # Create the user-notification relationship
    await crud_user_notification.create_for_user(
        session=session, user_id=user_id, notification_id=notification.id
    )

    return NotificationPublic.model_validate(notification)