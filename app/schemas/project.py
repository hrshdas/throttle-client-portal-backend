from datetime import date, datetime
from pydantic import BaseModel
from app.models.project import ProjectStatus, MilestoneStatus
from app.schemas.tasks import TaskResponse


class ProjectMilestoneResponse(BaseModel):
    id: str
    project_id: str
    organization_id: str
    title: str
    description: str | None
    status: MilestoneStatus
    human_status: str | None = None
    expected_date: date | None
    completed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ProjectMilestoneCreateRequest(BaseModel):
    title: str
    description: str | None = None
    status: MilestoneStatus = MilestoneStatus.UPCOMING
    expected_date: date | None = None


class ProjectResponse(BaseModel):
    id: str
    organization_id: str
    name: str
    description: str | None
    status: ProjectStatus
    human_status: str | None = None
    progress: int
    next_step: str | None
    expected_date: date | None
    created_at: datetime
    updated_at: datetime
    tasks: list[TaskResponse] = []
    milestones: list[ProjectMilestoneResponse] = []

    model_config = {"from_attributes": True}


class ProjectCreateRequest(BaseModel):
    organization_id: str | None = None
    name: str
    description: str | None = None
    status: ProjectStatus = ProjectStatus.RUNNING
    progress: int = 0
    next_step: str | None = None
    expected_date: date | None = None


class ProjectUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    status: ProjectStatus | None = None
    progress: int | None = None
    next_step: str | None = None
    expected_date: date | None = None
