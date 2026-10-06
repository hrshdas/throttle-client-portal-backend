from fastapi import APIRouter
from sqlalchemy import select, desc
from app.core.dependencies import DB, CurrentUser
from app.models.activity import Activity
from app.models.user import User
from app.schemas.activity import ActivityResponse

router = APIRouter(prefix="/activities", tags=["Activity Feed"])


@router.get("", response_model=list[ActivityResponse])
async def list_activities(current_user: CurrentUser, db: DB):
    """Fetch auto-populated activity feed for current user's organization."""
    res = await db.execute(
        select(Activity)
        .where(Activity.organization_id == current_user.organization_id)
        .order_by(desc(Activity.created_at))
        .limit(30)
    )
    activities = res.scalars().all()

    result = []
    for a in activities:
        actor_name = None
        user_id_to_check = a.actor_user_id or a.user_id
        if user_id_to_check:
            u_res = await db.execute(select(User).where(User.id == user_id_to_check))
            u = u_res.scalar_one_or_none()
            if u:
                actor_name = u.name

        result.append(
            ActivityResponse(
                id=a.id,
                organization_id=a.organization_id,
                user_id=a.user_id,
                actor_name=actor_name,
                type=a.type,
                description=a.description,
                created_at=a.created_at,
            )
        )
    return result
