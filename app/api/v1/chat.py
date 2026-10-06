import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload
from app.core.dependencies import DB, CurrentUser
from app.models.user import User, UserRole
from app.models.message import Conversation, ConversationParticipant, Message
from app.models.notification import NotificationType
from app.schemas.chat import ConversationResponse, MessageResponse, SendMessageRequest, ParticipantResponse
from app.services.notification_service import create_notification
from app.services.activity_service import create_activity
from app.core.crypto import encrypt_message, decrypt_message

router = APIRouter(prefix="/conversations", tags=["1-on-1 Encrypted Direct Chat"])


async def _get_or_create_direct_conversation(db: DB, current_user: User) -> Conversation:
    """
    Get or create a strict 1-on-1 direct encrypted conversation pairing between
    the current Client user and a Throttle Admin user.
    """
    # 1. Find primary Throttle Admin
    admin_res = await db.execute(select(User).where(User.role == UserRole.THROTTLE_ADMIN))
    admin_user = admin_res.scalars().first()
    if not admin_user:
        raise HTTPException(status_code=500, detail="System Throttle Admin account not configured")

    target_partner = admin_user if current_user.role != UserRole.THROTTLE_ADMIN else None

    # Search for an existing 1-on-1 direct conversation for current_user
    convs_res = await db.execute(
        select(Conversation)
        .options(
            selectinload(Conversation.participants).selectinload(ConversationParticipant.user),
            selectinload(Conversation.messages).selectinload(Message.sender),
        )
        .where(
            Conversation.organization_id == current_user.organization_id,
            Conversation.is_direct == True,
        )
    )
    existing_convs = convs_res.scalars().all()

    for c in existing_convs:
        participant_ids = {p.user_id for p in c.participants}
        if current_user.id in participant_ids and admin_user.id in participant_ids and len(participant_ids) <= 2:
            return c

    # Create new 1-on-1 direct conversation
    title_str = f"Direct: {current_user.name} & Throttle Admin" if target_partner else "Direct Support Channel"
    conv = Conversation(
        id=str(uuid.uuid4()),
        organization_id=current_user.organization_id,
        title=title_str,
        is_direct=True,
        is_encrypted=True,
    )
    db.add(conv)

    # Add current user
    p1 = ConversationParticipant(
        id=str(uuid.uuid4()),
        conversation_id=conv.id,
        user_id=current_user.id,
    )
    db.add(p1)

    # Add partner admin if current user is client
    if target_partner and target_partner.id != current_user.id:
        p2 = ConversationParticipant(
            id=str(uuid.uuid4()),
            conversation_id=conv.id,
            user_id=target_partner.id,
        )
        db.add(p2)

    await db.commit()

    # Re-fetch eager loaded
    res = await db.execute(
        select(Conversation)
        .options(
            selectinload(Conversation.participants).selectinload(ConversationParticipant.user),
            selectinload(Conversation.messages).selectinload(Message.sender),
        )
        .where(Conversation.id == conv.id)
    )
    return res.scalar_one()


@router.get("", response_model=list[ConversationResponse])
async def list_conversations(current_user: CurrentUser, db: DB):
    """List 1-on-1 direct encrypted conversations for the current user."""
    if current_user.role not in (UserRole.THROTTLE_ADMIN, UserRole.THROTTLE_STAFF):
        await _get_or_create_direct_conversation(db, current_user)

    query = (
        select(Conversation)
        .options(
            selectinload(Conversation.organization),
            selectinload(Conversation.participants).selectinload(ConversationParticipant.user),
            selectinload(Conversation.messages).selectinload(Message.sender),
        )
        .where(Conversation.is_direct == True)
    )

    if current_user.role not in (UserRole.THROTTLE_ADMIN, UserRole.THROTTLE_STAFF):
        query = query.where(Conversation.organization_id == current_user.organization_id)

    query = query.order_by(desc(Conversation.updated_at))
    res = await db.execute(query)
    convs = res.scalars().all()

    user_convs = []
    for conv in convs:
        participant_ids = {p.user_id for p in conv.participants}
        if current_user.id in participant_ids or current_user.role in (UserRole.THROTTLE_ADMIN, UserRole.THROTTLE_STAFF):
            user_convs.append(conv)

    result = []
    for conv in user_convs:
        participants_res = [
            ParticipantResponse(
                user_id=p.user_id,
                name=p.user.name if p.user else "Unknown",
                role=p.user.role.value if p.user else "CLIENT",
                avatar_url=p.user.avatar_url if p.user else None,
            )
            for p in conv.participants
        ]

        partner_p = next((p.user for p in conv.participants if p.user_id != current_user.id), None)
        if not partner_p and conv.participants:
            partner_p = conv.participants[0].user

        last_msg = None
        if conv.messages:
            sorted_msgs = sorted(conv.messages, key=lambda m: m.created_at, reverse=True)
            m = sorted_msgs[0]
            sender = m.sender
            decrypted_text = decrypt_message(m.message)
            last_msg = MessageResponse(
                id=m.id,
                conversation_id=m.conversation_id,
                organization_id=m.organization_id,
                sender_user_id=m.sender_user_id,
                sender_name=sender.name if sender else "Unknown",
                sender_avatar_url=sender.avatar_url if sender else None,
                sender_role=sender.role.value if sender else "CLIENT",
                message=decrypted_text,
                attachment_url=m.attachment_url,
                created_at=m.created_at,
                read_at=m.read_at,
            )

        unread_count = sum(
            1 for m in conv.messages
            if m.sender_user_id != current_user.id and m.read_at is None
        )

        # Effective timestamp for ordering
        effective_time = last_msg.created_at if last_msg else conv.updated_at

        result.append(
            ConversationResponse(
                id=conv.id,
                organization_id=conv.organization_id,
                organization_name=conv.organization.name if conv.organization else None,
                title=conv.title,
                is_direct=conv.is_direct,
                is_encrypted=conv.is_encrypted,
                partner_user_id=partner_p.id if partner_p else None,
                partner_name=partner_p.name if partner_p else "Throttle Admin",
                partner_avatar_url=partner_p.avatar_url if partner_p else None,
                partner_role=partner_p.role.value if partner_p else "THROTTLE_ADMIN",
                created_at=conv.created_at,
                updated_at=effective_time,
                participants=participants_res,
                unread_count=unread_count,
                last_message=last_msg,
            )
        )

    # Sort conversations by latest message timestamp descending so last-texted client is always at top
    result.sort(
        key=lambda item: item.last_message.created_at if item.last_message else item.updated_at,
        reverse=True,
    )

    return result


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
async def get_messages(conversation_id: str, current_user: CurrentUser, db: DB):
    """Get decrypted message history for 1-on-1 direct conversation."""
    res = await db.execute(
        select(Conversation)
        .options(selectinload(Conversation.participants))
        .where(Conversation.id == conversation_id)
    )
    conv = res.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Strict 1-on-1 participant access verification
    participant_ids = {p.user_id for p in conv.participants}
    if current_user.id not in participant_ids and current_user.role not in (UserRole.THROTTLE_ADMIN, UserRole.THROTTLE_STAFF):
        raise HTTPException(status_code=403, detail="Access denied to 1-on-1 conversation")

    msgs_res = await db.execute(
        select(Message)
        .options(selectinload(Message.sender))
        .where(Message.conversation_id == conversation_id, Message.deleted_at == None)
        .order_by(Message.created_at)
    )
    msgs = msgs_res.scalars().all()

    # Mark unread messages as read
    now = datetime.now(timezone.utc)
    updated_any = False
    for m in msgs:
        if m.sender_user_id != current_user.id and m.read_at is None:
            m.read_at = now
            updated_any = True

    if updated_any:
        await db.commit()

    return [
        MessageResponse(
            id=m.id,
            conversation_id=m.conversation_id,
            organization_id=m.organization_id,
            sender_user_id=m.sender_user_id,
            sender_name=m.sender.name if m.sender else "Unknown",
            sender_avatar_url=m.sender.avatar_url if m.sender else None,
            sender_role=m.sender.role.value if m.sender else "CLIENT",
            message=decrypt_message(m.message),
            attachment_url=m.attachment_url,
            created_at=m.created_at,
            read_at=m.read_at,
        )
        for m in msgs
    ]


@router.post("/{conversation_id}/read")
async def mark_conversation_read(conversation_id: str, current_user: CurrentUser, db: DB):
    """Explicitly mark all unread messages in a 1-on-1 conversation as read."""
    res = await db.execute(
        select(Conversation)
        .options(selectinload(Conversation.participants))
        .where(Conversation.id == conversation_id)
    )
    conv = res.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    participant_ids = {p.user_id for p in conv.participants}
    if current_user.id not in participant_ids and current_user.role not in (UserRole.THROTTLE_ADMIN, UserRole.THROTTLE_STAFF):
        raise HTTPException(status_code=403, detail="Access denied")

    msgs_res = await db.execute(
        select(Message).where(
            Message.conversation_id == conversation_id,
            Message.sender_user_id != current_user.id,
            Message.read_at == None,
        )
    )
    unread_msgs = msgs_res.scalars().all()
    now = datetime.now(timezone.utc)
    for m in unread_msgs:
        m.read_at = now

    if unread_msgs:
        await db.commit()

    return {"status": "success", "marked_read": len(unread_msgs)}


@router.post("/{conversation_id}/messages", response_model=MessageResponse)
async def send_message(conversation_id: str, req: SendMessageRequest, current_user: CurrentUser, db: DB):
    """Encrypt and post a message into 1-on-1 direct conversation."""
    res = await db.execute(
        select(Conversation)
        .options(selectinload(Conversation.participants))
        .where(Conversation.id == conversation_id)
    )
    conv = res.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Strict participant verification
    participant_ids = {p.user_id for p in conv.participants}
    if current_user.id not in participant_ids and current_user.role not in (UserRole.THROTTLE_ADMIN, UserRole.THROTTLE_STAFF):
        raise HTTPException(status_code=403, detail="Access denied to 1-on-1 conversation")

    # Encrypt plain message before database persistence
    encrypted_text = encrypt_message(req.message)

    msg = Message(
        id=str(uuid.uuid4()),
        conversation_id=conv.id,
        organization_id=conv.organization_id,
        sender_user_id=current_user.id,
        message=encrypted_text,
        attachment_url=req.attachment_url,
    )
    db.add(msg)
    conv.updated_at = datetime.now(timezone.utc)

    # Activity
    await create_activity(
        db=db,
        organization_id=conv.organization_id,
        actor_user_id=current_user.id,
        type_="message_sent",
        description=f"{current_user.name} sent an encrypted 1-on-1 message",
        entity_type="message",
        entity_id=msg.id,
    )

    # Notify conversation partner
    other_participants = [p for p in conv.participants if p.user_id != current_user.id]
    for p in other_participants:
        await create_notification(
            db=db,
            organization_id=conv.organization_id,
            recipient_user_id=p.user_id,
            type_=NotificationType.NEW_MESSAGE,
            title="New 1-on-1 Direct Message",
            message=f"{current_user.name} sent you a encrypted message",
            entity_type="conversation",
            entity_id=conv.id,
        )

    await db.commit()
    await db.refresh(msg)

    return MessageResponse(
        id=msg.id,
        conversation_id=msg.conversation_id,
        organization_id=msg.organization_id,
        sender_user_id=msg.sender_user_id,
        sender_name=current_user.name,
        sender_avatar_url=current_user.avatar_url,
        sender_role=current_user.role.value,
        message=req.message,  # Return plain text to author
        attachment_url=msg.attachment_url,
        created_at=msg.created_at,
        read_at=msg.read_at,
    )
