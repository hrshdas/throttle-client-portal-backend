import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select, desc
from app.core.dependencies import DB, CurrentUser
from app.models.user import User
from app.models.organization import Organization
from app.models.project import Project, Task
from app.models.message import Message
from app.models.activity import Activity
from app.schemas.user import UserResponse, UserUpdateRequest, OrganizationResponse
from app.schemas.project import ProjectResponse
from app.schemas.tasks import TaskResponse, TaskUpdateRequest
from app.schemas.message import MessageResponse, SendMessageRequest
from app.schemas.activity import ActivityResponse

router = APIRouter(prefix="/client", tags=["Client Portal"])


@router.get("/me")
async def get_current_user_profile(current_user: CurrentUser, db: DB):
    org_res = await db.execute(select(Organization).where(Organization.id == current_user.organization_id))
    org = org_res.scalar_one_or_none()

    return {
        "user": UserResponse.model_validate(current_user),
        "organization": OrganizationResponse.model_validate(org) if org else None,
    }


@router.patch("/me", response_model=UserResponse)
async def update_current_user_profile(req: UserUpdateRequest, current_user: CurrentUser, db: DB):
    if req.name is not None:
        current_user.name = req.name
    if req.phone is not None:
        current_user.phone = req.phone
    if req.avatar_url is not None:
        current_user.avatar_url = req.avatar_url

    await db.commit()
    await db.refresh(current_user)
    return current_user
