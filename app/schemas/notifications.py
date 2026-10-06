from datetime import datetime
from pydantic import BaseModel
from app.models.notification import NotificationType


class NotificationResponse(BaseModel):
    id: str
    organization_id: str
    recipient_user_id: str
    type: NotificationType
    title: str
    message: str
    entity_type: str | None
    entity_id: str | None
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}
