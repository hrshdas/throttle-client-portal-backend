import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.notification import Notification, NotificationType


async def create_notification(
    db: AsyncSession,
    organization_id: str,
    recipient_user_id: str,
    type_: NotificationType,
    title: str,
    message: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
) -> Notification:
    notif = Notification(
        id=str(uuid.uuid4()),
        organization_id=organization_id,
        recipient_user_id=recipient_user_id,
        type=type_,
        title=title,
        message=message,
        entity_type=entity_type,
        entity_id=entity_id,
        is_read=False,
    )
    db.add(notif)
    # caller handles commit or session flush
    return notif
