from datetime import datetime
from pydantic import BaseModel


class ParticipantResponse(BaseModel):
    user_id: str
    name: str
    role: str
    avatar_url: str | None


class MessageResponse(BaseModel):
    id: str
    conversation_id: str | None
    organization_id: str
    sender_user_id: str
    sender_name: str
    sender_avatar_url: str | None
    sender_role: str
    message: str
    attachment_url: str | None
    created_at: datetime
    read_at: datetime | None

    model_config = {"from_attributes": True}


class ConversationResponse(BaseModel):
    id: str
    organization_id: str
    organization_name: str | None = None
    title: str | None
    is_direct: bool = True
    is_encrypted: bool = True
    partner_user_id: str | None = None
    partner_name: str | None = None
    partner_avatar_url: str | None = None
    partner_role: str | None = None
    created_at: datetime
    updated_at: datetime
    participants: list[ParticipantResponse] = []
    unread_count: int = 0
    last_message: MessageResponse | None = None

    model_config = {"from_attributes": True}


class SendMessageRequest(BaseModel):
    message: str
    attachment_url: str | None = None
