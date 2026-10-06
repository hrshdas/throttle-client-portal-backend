from datetime import datetime
from pydantic import BaseModel, EmailStr
from app.models.user import UserRole


class UserResponse(BaseModel):
    id: str
    organization_id: str
    name: str
    email: EmailStr
    phone: str | None
    role: UserRole
    avatar_url: str | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdateRequest(BaseModel):
    name: str | None = None
    phone: str | None = None
    avatar_url: str | None = None


class OrganizationResponse(BaseModel):
    id: str
    name: str
    slug: str
    logo_url: str | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class OrganizationWithUserCount(OrganizationResponse):
    user_count: int
    project_count: int


class CreateOrganizationRequest(BaseModel):
    name: str
    slug: str
    logo_url: str | None = None


class InviteUserRequest(BaseModel):
    email: EmailStr
    name: str | None = None
    role: UserRole = UserRole.CLIENT


class DisableUserRequest(BaseModel):
    is_active: bool
