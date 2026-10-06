from datetime import date, datetime
from pydantic import BaseModel
from app.models.project import TaskStatus, TaskPriority, ApprovalStatus
from app.schemas.user import UserResponse


class TaskApprovalHistoryResponse(BaseModel):
    id: str
    task_id: str
    organization_id: str
    user_id: str
    user_name: str | None = None
    action: str
    comment: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TaskCommentResponse(BaseModel):
    id: str
    task_id: str
    organization_id: str
    user_id: str
    user_name: str | None = None
    user_role: str | None = None
    user_avatar_url: str | None = None
    message: str
    attachment_url: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TaskCommentCreateRequest(BaseModel):
    message: str
    attachment_url: str | None = None


class TaskResponse(BaseModel):
    id: str
    organization_id: str
    project_id: str | None
    project_name: str | None = None
    title: str
    description: str | None
    status: TaskStatus
    human_status: str | None = None
    priority: TaskPriority
    assigned_to_user_id: str | None
    assigned_to_user_name: str | None = None
    created_by_user_id: str | None
    created_by_user_name: str | None = None
    due_date: date | None
    requires_client_approval: bool
    approval_status: ApprovalStatus
    human_approval_status: str | None = None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    comments: list[TaskCommentResponse] = []
    approval_history: list[TaskApprovalHistoryResponse] = []

    model_config = {"from_attributes": True}


class TaskCreateRequest(BaseModel):
    organization_id: str | None = None  # Admin can specify, or derived from current_user
    project_id: str | None = None
    title: str
    description: str | None = None
    priority: TaskPriority = TaskPriority.MEDIUM
    assigned_to_user_id: str | None = None
    due_date: date | None = None
    requires_client_approval: bool = False


class TaskUpdateRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    assigned_to_user_id: str | None = None
    due_date: date | None = None
    requires_client_approval: bool | None = None


class TaskApproveRequest(BaseModel):
    comment: str | None = None


class TaskRequestChangesRequest(BaseModel):
    comment: str
