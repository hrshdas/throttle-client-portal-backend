import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload
from app.core.dependencies import DB, CurrentUser, AdminUser
from app.models.user import UserRole
from app.models.project import Project, ProjectMilestone, Task, ProjectStatus, MilestoneStatus
from app.schemas.project import (
    ProjectResponse,
    ProjectCreateRequest,
    ProjectUpdateRequest,
    ProjectMilestoneResponse,
    ProjectMilestoneCreateRequest,
)
from app.api.v1.tasks import _build_task_response
from app.services.activity_service import create_activity
from app.core.utils import get_human_status

router = APIRouter(prefix="/projects", tags=["Projects & Milestones"])


def _build_milestone_response(m: ProjectMilestone) -> ProjectMilestoneResponse:
    return ProjectMilestoneResponse(
        id=m.id,
        project_id=m.project_id,
        organization_id=m.organization_id,
        title=m.title,
        description=m.description,
        status=m.status,
        human_status=get_human_status(m.status.value),
        expected_date=m.expected_date,
        completed_at=m.completed_at,
        created_at=m.created_at,
    )


def _build_project_response(p: Project) -> ProjectResponse:
    tasks_res = [_build_task_response(t) for t in (p.tasks or [])]
    milestones_res = [_build_milestone_response(m) for m in (p.milestones or [])]

    return ProjectResponse(
        id=p.id,
        organization_id=p.organization_id,
        name=p.name,
        description=p.description,
        status=p.status,
        human_status=get_human_status(p.status.value),
        progress=p.progress,
        next_step=p.next_step,
        expected_date=p.expected_date,
        created_at=p.created_at,
        updated_at=p.updated_at,
        tasks=tasks_res,
        milestones=milestones_res,
    )


@router.get("", response_model=list[ProjectResponse])
async def list_projects(current_user: CurrentUser, db: DB):
    """List projects belonging to current user's organization."""
    query = (
        select(Project)
        .options(
            selectinload(Project.tasks).selectinload(Task.project),
            selectinload(Project.tasks).selectinload(Task.assigned_user),
            selectinload(Project.tasks).selectinload(Task.creator_user),
            selectinload(Project.tasks).selectinload(Task.comments),
            selectinload(Project.tasks).selectinload(Task.approval_history),
            selectinload(Project.milestones),
        )
        .order_by(desc(Project.created_at))
    )

    if current_user.role not in (UserRole.THROTTLE_ADMIN, UserRole.THROTTLE_STAFF):
        query = query.where(Project.organization_id == current_user.organization_id)

    res = await db.execute(query)
    projects = res.scalars().all()
    return [_build_project_response(p) for p in projects]


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project_detail(project_id: str, current_user: CurrentUser, db: DB):
    """Get single project detail."""
    query = (
        select(Project)
        .options(
            selectinload(Project.tasks).selectinload(Task.project),
            selectinload(Project.tasks).selectinload(Task.assigned_user),
            selectinload(Project.tasks).selectinload(Task.creator_user),
            selectinload(Project.tasks).selectinload(Task.comments),
            selectinload(Project.tasks).selectinload(Task.approval_history),
            selectinload(Project.milestones),
        )
        .where(Project.id == project_id)
    )

    if current_user.role not in (UserRole.THROTTLE_ADMIN, UserRole.THROTTLE_STAFF):
        query = query.where(Project.organization_id == current_user.organization_id)

    res = await db.execute(query)
    proj = res.scalar_one_or_none()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found or access denied")

    return _build_project_response(proj)


@router.post("", response_model=ProjectResponse)
async def create_project(req: ProjectCreateRequest, current_user: CurrentUser, db: DB):
    """Create a new project."""
    target_org_id = current_user.organization_id
    if current_user.role in (UserRole.THROTTLE_ADMIN, UserRole.THROTTLE_STAFF) and req.organization_id:
        target_org_id = req.organization_id

    proj = Project(
        id=str(uuid.uuid4()),
        organization_id=target_org_id,
        name=req.name,
        description=req.description,
        status=req.status,
        progress=req.progress,
        next_step=req.next_step,
        expected_date=req.expected_date,
    )
    db.add(proj)

    await create_activity(
        db=db,
        organization_id=target_org_id,
        actor_user_id=current_user.id,
        type_="project_created",
        description=f"{current_user.name} created project: {proj.name}",
        entity_type="project",
        entity_id=proj.id,
    )

    await db.commit()
    return await get_project_detail(proj.id, current_user, db)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(project_id: str, req: ProjectUpdateRequest, current_user: CurrentUser, db: DB):
    """Update project status, progress, or next step."""
    res = await db.execute(select(Project).where(Project.id == project_id))
    proj = res.scalar_one_or_none()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    if current_user.role not in (UserRole.THROTTLE_ADMIN, UserRole.THROTTLE_STAFF) and proj.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="Project not found or access denied")

    if req.name is not None:
        proj.name = req.name
    if req.description is not None:
        proj.description = req.description
    if req.status is not None:
        proj.status = req.status
    if req.progress is not None:
        proj.progress = req.progress
    if req.next_step is not None:
        proj.next_step = req.next_step
    if req.expected_date is not None:
        proj.expected_date = req.expected_date

    proj.updated_at = datetime.now(timezone.utc)

    await create_activity(
        db=db,
        organization_id=proj.organization_id,
        actor_user_id=current_user.id,
        type_="project_updated",
        description=f"Project status updated to {get_human_status(proj.status.value)}: {proj.name}",
        entity_type="project",
        entity_id=proj.id,
    )

    await db.commit()
    return await get_project_detail(proj.id, current_user, db)


@router.get("/{project_id}/milestones", response_model=list[ProjectMilestoneResponse])
async def list_project_milestones(project_id: str, current_user: CurrentUser, db: DB):
    """List milestones for a project."""
    res = await db.execute(
        select(ProjectMilestone)
        .where(ProjectMilestone.project_id == project_id)
        .order_by(ProjectMilestone.expected_date)
    )
    ms = res.scalars().all()
    return [_build_milestone_response(m) for m in ms]


@router.post("/{project_id}/milestones", response_model=ProjectMilestoneResponse)
async def create_project_milestone(project_id: str, req: ProjectMilestoneCreateRequest, current_user: CurrentUser, db: DB):
    """Create a milestone for a project."""
    res = await db.execute(select(Project).where(Project.id == project_id))
    proj = res.scalar_one_or_none()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    m = ProjectMilestone(
        id=str(uuid.uuid4()),
        project_id=proj.id,
        organization_id=proj.organization_id,
        title=req.title,
        description=req.description,
        status=req.status,
        expected_date=req.expected_date,
    )
    db.add(m)
    await db.commit()
    await db.refresh(m)
    return _build_milestone_response(m)
