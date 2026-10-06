from datetime import datetime
from pydantic import BaseModel


class MessageResponse(BaseModel):
    id: str
    organization_id: str
    sender_user_id: str
    sender_name: str
    sender_avatar_url: str | None
    sender_role: str
    message: str
    attachment_url: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class SendMessageRequest(BaseModel):
    message: str
    attachment_url: str | None = None
