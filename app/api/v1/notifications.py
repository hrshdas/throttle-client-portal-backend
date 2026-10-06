from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select, desc
from app.core.dependencies import DB, CurrentUser
from app.models.notification import Notification
from app.schemas.notifications import NotificationResponse

router = APIRouter(prefix="/notifications", tags=["Notification System"])


@router.get("", response_model=list[NotificationResponse])
async def list_notifications(current_user: CurrentUser, db: DB):
    """List targeted notifications for current authenticated user."""
    res = await db.execute(
        select(Notification)
        .where(Notification.recipient_user_id == current_user.id)
        .order_by(desc(Notification.created_at))
        .limit(50)
    )
    notifs = res.scalars().all()
    return notifs


@router.post("/{notification_id}/read", response_model=NotificationResponse)
async def mark_notification_read(notification_id: str, current_user: CurrentUser, db: DB):
    """Mark a single notification as read."""
    res = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.recipient_user_id == current_user.id,
        )
    )
    notif = res.scalar_one_or_none()
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")

    notif.is_read = True
    await db.commit()
    await db.refresh(notif)
    return notif


@router.post("/read-all")
async def mark_all_notifications_read(current_user: CurrentUser, db: DB):
    """Mark all notifications for current user as read."""
    res = await db.execute(
        select(Notification).where(
            Notification.recipient_user_id == current_user.id,
            Notification.is_read == False,
        )
    )
    notifs = res.scalars().all()
    for n in notifs:
        n.is_read = True

    await db.commit()
    return {"message": "All notifications marked as read"}
