from datetime import datetime
from pydantic import BaseModel
from app.models.meta import MetaConnectionStatus


class MetaConnectionResponse(BaseModel):
    """Safe connection status — never exposes access tokens."""
    id: str
    organization_id: str
    meta_user_id: str | None = None
    business_id: str | None = None
    ad_account_id: str | None = None
    ad_account_name: str | None = None
    status: MetaConnectionStatus
    error_message: str | None = None
    last_synced_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class MetaConnectStartResponse(BaseModel):
    """Response for POST /meta/connect/start — URL to redirect user to Meta."""
    auth_url: str
    state: str


class MetaSelectAdAccountRequest(BaseModel):
    """Request body for POST /meta/select-ad-account."""
    ad_account_id: str
    ad_account_name: str | None = None


class MetaAdAccountResponse(BaseModel):
    """A single accessible Meta ad account."""
    id: str
    name: str
    currency: str = "USD"
