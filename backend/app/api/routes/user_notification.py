import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, SessionDep
from app.features.user.crud.notification import (
    crud_notification,
    crud_user_notification,
)
from app.features.user.models.notification import (
    NotificationCreate,
    NotificationPublic,
    NotificationsPublic,
    NotificationUpdate,
)

router = APIRouter()


def _check_permission(
    current_user_id: uuid.UUID, user_id: uuid.UUID, is_admin: bool = False
) -> bool:
    """Check if current user can access resource for given user_id."""
    return current_user_id == user_id or is_admin


@router.get("/users/{user_id}/notifications", response_model=NotificationsPublic)
async def get_user_notifications(
    session: SessionDep,
    current_user: CurrentUser,
    user_id: uuid.UUID,
    skip: int = 0,
    limit: int = 100,
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
    """Get count of unread notifications for a user."""
    if not _check_permission(current_user.id, user_id, current_user.is_superuser):
        raise HTTPException(status_code=403, detail="Not authorized")

    count = await crud_notification.count_by_user(
        session=session, user_id=user_id, unread_only=True
    )
    return {"unread_count": count}


@router.get(
    "/users/{user_id}/notifications/{notification_id}",
    response_model=NotificationPublic,
)
async def get_user_notification(
    session: SessionDep,
    current_user: CurrentUser,
    user_id: uuid.UUID,
    notification_id: uuid.UUID,
) -> NotificationPublic:
    """Get a specific notification for a user."""
    if not _check_permission(current_user.id, user_id, current_user.is_superuser):
        raise HTTPException(status_code=403, detail="Not authorized")

    notification = await crud_notification.get_user_notification(
        session=session, notification_id=notification_id, user_id=user_id
    )
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
    """Mark a notification as read for a user."""
    if not _check_permission(current_user.id, user_id, current_user.is_superuser):
        raise HTTPException(status_code=403, detail="Not authorized")

    # First verify the notification exists for the user
    notification = await crud_notification.get_user_notification(
        session=session, notification_id=notification_id, user_id=user_id
    )
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    user_notification = await crud_user_notification.mark_as_read(
        session=session, notification_id=notification_id, user_id=user_id
    )

    if not user_notification:
        raise HTTPException(status_code=404, detail="User notification not found")

    return {"message": "Notification marked as read", "success": True}


@router.patch("/users/{user_id}/notifications/read-all")
async def mark_all_notifications_as_read(
    session: SessionDep,
    current_user: CurrentUser,
    user_id: uuid.UUID,
) -> dict:
    """Mark all notifications as read for a user."""
    if not _check_permission(current_user.id, user_id, current_user.is_superuser):
        raise HTTPException(status_code=403, detail="Not authorized")

    count = await crud_user_notification.mark_all_as_read(
        session=session, user_id=user_id
    )

    return {"message": f"Marked {count} notifications as read", "marked_count": count}


# Admin endpoints for creating notifications
@router.post(
    "/notifications",
    response_model=NotificationPublic,
    status_code=status.HTTP_201_CREATED,
)
async def create_notification(
    session: SessionDep,
    current_user: CurrentUser,
    notification_in: NotificationCreate,
    user_ids: list[uuid.UUID],
) -> NotificationPublic:
    """Create a new notification and assign it to users (admin only)."""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403, detail="Not authorized. Admin access required."
        )

    if not user_ids:
        raise HTTPException(status_code=400, detail="At least one user ID is required")

    notification = await crud_notification.create_for_users(
        session=session,
        obj_in=notification_in,
        user_ids=user_ids,
        current_user=current_user.id,
    )
    return NotificationPublic.model_validate(notification)


@router.get("/notifications", response_model=NotificationsPublic)
async def get_all_notifications(
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 100,
) -> NotificationsPublic:
    """Get all notifications (admin only)."""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403, detail="Not authorized. Admin access required."
        )

    notifications = await crud_notification.get_multi(
        session=session, skip=skip, limit=limit
    )
    count = await crud_notification.count(session=session)
    return NotificationsPublic(data=notifications, count=count)


@router.get("/notifications/{notification_id}", response_model=NotificationPublic)
async def get_notification(
    session: SessionDep,
    current_user: CurrentUser,
    notification_id: uuid.UUID,
) -> NotificationPublic:
    """Get a specific notification (admin only)."""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403, detail="Not authorized. Admin access required."
        )

    notification = await crud_notification.get(session=session, id=notification_id)
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    return NotificationPublic.model_validate(notification)


@router.patch("/notifications/{notification_id}", response_model=NotificationPublic)
async def update_notification(
    session: SessionDep,
    current_user: CurrentUser,
    notification_id: uuid.UUID,
    notification_update: NotificationUpdate,
) -> NotificationPublic:
    """Update a specific notification (admin only)."""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403, detail="Not authorized. Admin access required."
        )

    notification = await crud_notification.get(session=session, id=notification_id)
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    updated_notification = await crud_notification.update(
        session=session, db_obj=notification, obj_in=notification_update
    )
    return NotificationPublic.model_validate(updated_notification)


@router.delete(
    "/notifications/{notification_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_notification(
    session: SessionDep,
    current_user: CurrentUser,
    notification_id: uuid.UUID,
) -> None:
    """Delete a specific notification (admin only)."""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403, detail="Not authorized. Admin access required."
        )

    notification = await crud_notification.get(session=session, id=notification_id)
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    await crud_notification.remove(session=session, id=notification_id)
