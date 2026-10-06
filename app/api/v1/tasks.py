import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload
from app.core.dependencies import DB, CurrentUser, AdminUser
from app.models.user import User, UserRole
from app.models.project import Task, TaskComment, TaskApprovalHistory, TaskStatus, ApprovalStatus
from app.models.notification import NotificationType
from app.schemas.tasks import (
    TaskResponse,
    TaskCreateRequest,
    TaskUpdateRequest,
    TaskApproveRequest,
    TaskRequestChangesRequest,
    TaskCommentResponse,
    TaskCommentCreateRequest,
    TaskApprovalHistoryResponse,
)
from app.services.notification_service import create_notification
from app.services.activity_service import create_activity
from app.core.utils import get_human_status, get_human_approval_status

router = APIRouter(prefix="/tasks", tags=["Task System"])


def _build_task_response(task: Task) -> TaskResponse:
    comment_responses = []
    for c in (task.comments or []):
        sender = c.user
        comment_responses.append(
            TaskCommentResponse(
                id=c.id,
                task_id=c.task_id,
                organization_id=c.organization_id,
                user_id=c.user_id,
                user_name=sender.name if sender else None,
                user_role=sender.role.value if sender else None,
                user_avatar_url=sender.avatar_url if sender else None,
                message=c.message,
                attachment_url=c.attachment_url,
                created_at=c.created_at,
            )
        )

    history_responses = []
    for h in (task.approval_history or []):
        u = h.user
        history_responses.append(
            TaskApprovalHistoryResponse(
                id=h.id,
                task_id=h.task_id,
                organization_id=h.organization_id,
                user_id=h.user_id,
                user_name=u.name if u else None,
                action=h.action,
                comment=h.comment,
                created_at=h.created_at,
            )
        )

    return TaskResponse(
        id=task.id,
        organization_id=task.organization_id,
        project_id=task.project_id,
        project_name=task.project.name if task.project else None,
        title=task.title,
        description=task.description,
        status=task.status,
        human_status=get_human_status(task.status.value),
        priority=task.priority,
        assigned_to_user_id=task.assigned_to_user_id,
        assigned_to_user_name=task.assigned_user.name if task.assigned_user else None,
        created_by_user_id=task.created_by_user_id,
        created_by_user_name=task.creator_user.name if task.creator_user else None,
        due_date=task.due_date,
        requires_client_approval=task.requires_client_approval,
        approval_status=task.approval_status,
        human_approval_status=get_human_approval_status(task.approval_status.value),
        completed_at=task.completed_at,
        created_at=task.created_at,
        updated_at=task.updated_at,
        comments=comment_responses,
        approval_history=history_responses,
    )


@router.get("", response_model=list[TaskResponse])
async def list_tasks(
    current_user: CurrentUser,
    db: DB,
    status: TaskStatus | None = None,
    organization_id: str | None = None,
):
    """List tasks for the current user's organization (or all/filtered if THROTTLE_ADMIN)."""
    query = select(Task).options(
        selectinload(Task.project),
        selectinload(Task.assigned_user),
        selectinload(Task.creator_user),
        selectinload(Task.comments).selectinload(TaskComment.user),
        selectinload(Task.approval_history).selectinload(TaskApprovalHistory.user),
    )

    if current_user.role not in (UserRole.THROTTLE_ADMIN, UserRole.THROTTLE_STAFF):
        query = query.where(Task.organization_id == current_user.organization_id)
    elif organization_id:
        query = query.where(Task.organization_id == organization_id)

    if status:
        query = query.where(Task.status == status)

    query = query.order_by(desc(Task.created_at))
    res = await db.execute(query)
    tasks = res.scalars().all()
    return [_build_task_response(t) for t in tasks]


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task_detail(task_id: str, current_user: CurrentUser, db: DB):
    """Fetch a single task by ID with comments and approval history. Enforces tenant boundary."""
    query = (
        select(Task)
        .options(
            selectinload(Task.project),
            selectinload(Task.assigned_user),
            selectinload(Task.creator_user),
            selectinload(Task.comments).selectinload(TaskComment.user),
            selectinload(Task.approval_history).selectinload(TaskApprovalHistory.user),
        )
        .where(Task.id == task_id)
    )

    if current_user.role not in (UserRole.THROTTLE_ADMIN, UserRole.THROTTLE_STAFF):
        query = query.where(Task.organization_id == current_user.organization_id)

    res = await db.execute(query)
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found or access denied")

    return _build_task_response(task)


@router.post("", response_model=TaskResponse)
async def create_task(req: TaskCreateRequest, current_user: CurrentUser, db: DB):
    """Create a new task. Admin can specify organization_id; Client uses current org."""
    target_org_id = current_user.organization_id
    if current_user.role in (UserRole.THROTTLE_ADMIN, UserRole.THROTTLE_STAFF) and req.organization_id:
        target_org_id = req.organization_id

    app_status = ApprovalStatus.PENDING if req.requires_client_approval else ApprovalStatus.NOT_REQUIRED

    task = Task(
        id=str(uuid.uuid4()),
        organization_id=target_org_id,
        project_id=req.project_id,
        title=req.title,
        description=req.description,
        status=TaskStatus.TODO,
        priority=req.priority,
        assigned_to_user_id=req.assigned_to_user_id,
        created_by_user_id=current_user.id,
        due_date=req.due_date,
        requires_client_approval=req.requires_client_approval,
        approval_status=app_status,
    )
    db.add(task)

    # Activity
    await create_activity(
        db=db,
        organization_id=target_org_id,
        actor_user_id=current_user.id,
        type_="task_created",
        description=f"{current_user.name} created task: {task.title}",
        entity_type="task",
        entity_id=task.id,
    )

    # Notification if assigned
    if req.assigned_to_user_id and req.assigned_to_user_id != current_user.id:
        await create_notification(
            db=db,
            organization_id=target_org_id,
            recipient_user_id=req.assigned_to_user_id,
            type_=NotificationType.TASK_ASSIGNED,
            title="New Task Assigned",
            message=f"You have been assigned: {task.title}",
            entity_type="task",
            entity_id=task.id,
        )

    await db.commit()

    # Re-query to return eager loaded task
    return await get_task_detail(task.id, current_user, db)


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(task_id: str, req: TaskUpdateRequest, current_user: CurrentUser, db: DB):
    """Update task details/status."""
    res = await db.execute(select(Task).where(Task.id == task_id))
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if current_user.role not in (UserRole.THROTTLE_ADMIN, UserRole.THROTTLE_STAFF) and task.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="Task not found or access denied")

    if req.title is not None:
        task.title = req.title
    if req.description is not None:
        task.description = req.description
    if req.status is not None:
        task.status = req.status
        if req.status == TaskStatus.COMPLETED and not task.completed_at:
            task.completed_at = datetime.now(timezone.utc)
    if req.priority is not None:
        task.priority = req.priority
    if req.assigned_to_user_id is not None:
        task.assigned_to_user_id = req.assigned_to_user_id
    if req.due_date is not None:
        task.due_date = req.due_date
    if req.requires_client_approval is not None:
        task.requires_client_approval = req.requires_client_approval
        if req.requires_client_approval and task.approval_status == ApprovalStatus.NOT_REQUIRED:
            task.approval_status = ApprovalStatus.PENDING

    task.updated_at = datetime.now(timezone.utc)

    # Activity
    await create_activity(
        db=db,
        organization_id=task.organization_id,
        actor_user_id=current_user.id,
        type_="task_updated",
        description=f"{current_user.name} updated task: {task.title}",
        entity_type="task",
        entity_id=task.id,
    )

    await db.commit()
    return await get_task_detail(task.id, current_user, db)


@router.post("/{task_id}/approve", response_model=TaskResponse)
async def approve_task(task_id: str, req: TaskApproveRequest, current_user: CurrentUser, db: DB):
    """Approve a task assigned for review. Enforces that only client users can approve."""
    if current_user.role in (UserRole.THROTTLE_ADMIN, UserRole.THROTTLE_STAFF):
        raise HTTPException(
            status_code=403,
            detail="Only client users can approve tasks requiring client approval.",
        )

    res = await db.execute(select(Task).where(Task.id == task_id))
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="Task not found or access denied")

    # Update task approval status
    task.approval_status = ApprovalStatus.APPROVED
    task.status = TaskStatus.COMPLETED
    task.completed_at = datetime.now(timezone.utc)

    # Record in approval history
    history_entry = TaskApprovalHistory(
        id=str(uuid.uuid4()),
        task_id=task.id,
        organization_id=task.organization_id,
        user_id=current_user.id,
        action="APPROVED",
        comment=req.comment,
    )
    db.add(history_entry)

    # Record Activity
    await create_activity(
        db=db,
        organization_id=task.organization_id,
        actor_user_id=current_user.id,
        type_="task_approved",
        description=f"{current_user.name} approved task: {task.title}",
        entity_type="task",
        entity_id=task.id,
    )

    # Notify task creator / admin
    if task.created_by_user_id and task.created_by_user_id != current_user.id:
        await create_notification(
            db=db,
            organization_id=task.organization_id,
            recipient_user_id=task.created_by_user_id,
            type_=NotificationType.TASK_APPROVED,
            title="Task Approved",
            message=f"{current_user.name} approved: {task.title}",
            entity_type="task",
            entity_id=task.id,
        )

    await db.commit()
    return await get_task_detail(task.id, current_user, db)


@router.post("/{task_id}/request-changes", response_model=TaskResponse)
async def request_changes(task_id: str, req: TaskRequestChangesRequest, current_user: CurrentUser, db: DB):
    """Request changes on a task. Enforces that only client users can request changes."""
    if current_user.role in (UserRole.THROTTLE_ADMIN, UserRole.THROTTLE_STAFF):
        raise HTTPException(
            status_code=403,
            detail="Only client users can request changes on tasks requiring client approval.",
        )

    res = await db.execute(select(Task).where(Task.id == task_id))
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="Task not found or access denied")

    task.approval_status = ApprovalStatus.CHANGES_REQUESTED
    task.status = TaskStatus.IN_PROGRESS

    # Record in approval history
    history_entry = TaskApprovalHistory(
        id=str(uuid.uuid4()),
        task_id=task.id,
        organization_id=task.organization_id,
        user_id=current_user.id,
        action="CHANGES_REQUESTED",
        comment=req.comment,
    )
    db.add(history_entry)

    # Store comment in task_comments
    comment_entry = TaskComment(
        id=str(uuid.uuid4()),
        task_id=task.id,
        organization_id=task.organization_id,
        user_id=current_user.id,
        message=f"[Changes Requested] {req.comment}",
    )
    db.add(comment_entry)

    # Record Activity
    await create_activity(
        db=db,
        organization_id=task.organization_id,
        actor_user_id=current_user.id,
        type_="changes_requested",
        description=f"{current_user.name} requested changes on: {task.title}",
        entity_type="task",
        entity_id=task.id,
    )

    # Notify creator/admin
    if task.created_by_user_id and task.created_by_user_id != current_user.id:
        await create_notification(
            db=db,
            organization_id=task.organization_id,
            recipient_user_id=task.created_by_user_id,
            type_=NotificationType.CHANGES_REQUESTED,
            title="Changes Requested",
            message=f"{current_user.name} requested changes on: {task.title}",
            entity_type="task",
            entity_id=task.id,
        )

    await db.commit()
    return await get_task_detail(task.id, current_user, db)


@router.get("/{task_id}/comments", response_model=list[TaskCommentResponse])
async def list_task_comments(task_id: str, current_user: CurrentUser, db: DB):
    """Fetch comments for a task."""
    res = await db.execute(
        select(TaskComment)
        .options(selectinload(TaskComment.user))
        .where(TaskComment.task_id == task_id)
        .order_by(TaskComment.created_at)
    )
    comments = res.scalars().all()
    return [
        TaskCommentResponse(
            id=c.id,
            task_id=c.task_id,
            organization_id=c.organization_id,
            user_id=c.user_id,
            user_name=c.user.name if c.user else None,
            user_role=c.user.role.value if c.user else None,
            user_avatar_url=c.user.avatar_url if c.user else None,
            message=c.message,
            attachment_url=c.attachment_url,
            created_at=c.created_at,
        )
        for c in comments
    ]


@router.post("/{task_id}/comments", response_model=TaskCommentResponse)
async def add_task_comment(task_id: str, req: TaskCommentCreateRequest, current_user: CurrentUser, db: DB):
    """Add a comment to a task and notify creator/assignee."""
    res = await db.execute(select(Task).where(Task.id == task_id))
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if current_user.role not in (UserRole.THROTTLE_ADMIN, UserRole.THROTTLE_STAFF) and task.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="Task not found or access denied")

    comment = TaskComment(
        id=str(uuid.uuid4()),
        task_id=task.id,
        organization_id=task.organization_id,
        user_id=current_user.id,
        message=req.message,
        attachment_url=req.attachment_url,
    )
    db.add(comment)

    # Activity
    await create_activity(
        db=db,
        organization_id=task.organization_id,
        actor_user_id=current_user.id,
        type_="task_comment",
        description=f"{current_user.name} commented on: {task.title}",
        entity_type="task",
        entity_id=task.id,
    )

    # Notify recipient (assigned user or creator)
    target_user_id = task.assigned_to_user_id if current_user.id != task.assigned_to_user_id else task.created_by_user_id
    if target_user_id and target_user_id != current_user.id:
        await create_notification(
            db=db,
            organization_id=task.organization_id,
            recipient_user_id=target_user_id,
            type_=NotificationType.TASK_COMMENT_ADDED,
            title="New Task Comment",
            message=f"{current_user.name} commented on: {task.title}",
            entity_type="task",
            entity_id=task.id,
        )

    await db.commit()
    await db.refresh(comment)

    return TaskCommentResponse(
        id=comment.id,
        task_id=comment.task_id,
        organization_id=comment.organization_id,
        user_id=comment.user_id,
        user_name=current_user.name,
        user_role=current_user.role.value,
        user_avatar_url=current_user.avatar_url,
        message=comment.message,
        attachment_url=comment.attachment_url,
        created_at=comment.created_at,
    )
