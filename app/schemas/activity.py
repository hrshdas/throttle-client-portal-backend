from datetime import datetime
from pydantic import BaseModel


class ActivityResponse(BaseModel):
    id: str
    organization_id: str
    user_id: str | None
    actor_name: str | None = None
    type: str
    description: str
    created_at: datetime

    model_config = {"from_attributes": True}
