import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select, func, desc
from app.core.dependencies import DB, AdminUser
from app.models.organization import Organization
from app.models.user import User
from app.models.invitation import Invitation, InvitationStatus
from app.models.project import Project, Task
from app.schemas.user import (
    OrganizationResponse,
    OrganizationWithUserCount,
    CreateOrganizationRequest,
    UserResponse,
    InviteUserRequest,
    DisableUserRequest,
)
from app.core.config import get_settings

settings = get_settings()

router = APIRouter(prefix="/admin", tags=["Agency Admin"])


@router.get("/organizations", response_model=list[OrganizationWithUserCount])
async def list_organizations(admin_user: AdminUser, db: DB):
    res = await db.execute(select(Organization).order_by(desc(Organization.created_at)))
    orgs = res.scalars().all()

    result = []
    for org in orgs:
        u_count_res = await db.execute(
            select(func.count(User.id)).where(User.organization_id == org.id)
        )
        u_count = u_count_res.scalar() or 0

        p_count_res = await db.execute(
            select(func.count(Project.id)).where(Project.organization_id == org.id)
        )
        p_count = p_count_res.scalar() or 0

        result.append(
            OrganizationWithUserCount(
                id=org.id,
                name=org.name,
                slug=org.slug,
                logo_url=org.logo_url,
                is_active=org.is_active,
                created_at=org.created_at,
                user_count=u_count,
                project_count=p_count,
            )
        )
    return result


@router.post("/organizations", response_model=OrganizationResponse)
async def create_organization(req: CreateOrganizationRequest, admin_user: AdminUser, db: DB):
    # Check slug collision
    existing = await db.execute(select(Organization).where(Organization.slug == req.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Organization slug already exists")

    org = Organization(
        id=str(uuid.uuid4()),
        name=req.name,
        slug=req.slug.lower(),
        logo_url=req.logo_url,
    )
    db.add(org)
    await db.commit()
    await db.refresh(org)
    return org


@router.get("/organizations/{org_id}/users", response_model=list[UserResponse])
async def list_organization_users(org_id: str, admin_user: AdminUser, db: DB):
    res = await db.execute(
        select(User).where(User.organization_id == org_id).order_by(User.name)
    )
    users = res.scalars().all()
    return users


@router.post("/organizations/{org_id}/invite")
async def invite_user(org_id: str, req: InviteUserRequest, admin_user: AdminUser, db: DB):
    org_res = await db.execute(select(Organization).where(Organization.id == org_id))
    org = org_res.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    token = str(uuid.uuid4())
    inv = Invitation(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        email=req.email.lower(),
        name=req.name,
        role=req.role,
        token=token,
        status=InvitationStatus.PENDING,
        created_by_user_id=admin_user.id,
    )
    db.add(inv)
    await db.commit()

    invite_url = f"{settings.FRONTEND_URL}/accept-invitation?token={token}"
    print(f"\n[DEV] Invitation generated for {req.email} ({org.name}): {invite_url}\n")

    return {
        "message": f"Invitation generated for {req.email}",
        "invite_token": token,
        "invite_url": invite_url,
    }


@router.patch("/users/{user_id}/disable", response_model=UserResponse)
async def toggle_user_status(user_id: str, req: DisableUserRequest, admin_user: AdminUser, db: DB):
    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = req.is_active
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/stats")
async def get_system_stats(admin_user: AdminUser, db: DB):
    org_count = (await db.execute(select(func.count(Organization.id)))).scalar() or 0
    user_count = (await db.execute(select(func.count(User.id)))).scalar() or 0
    proj_count = (await db.execute(select(func.count(Project.id)))).scalar() or 0
    task_count = (await db.execute(select(func.count(Task.id)))).scalar() or 0

    return {
        "total_organizations": org_count,
        "total_users": user_count,
        "total_projects": proj_count,
        "total_tasks": task_count,
    }
