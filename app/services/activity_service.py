import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.activity import Activity


async def create_activity(
    db: AsyncSession,
    organization_id: str,
    actor_user_id: str | None,
    type_: str,
    description: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    metadata: dict | None = None,
) -> Activity:
    act = Activity(
        id=str(uuid.uuid4()),
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        user_id=actor_user_id,
        type=type_,
        description=description,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata_=metadata,
    )
    db.add(act)
    return act
