import re
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy import select
from app.core.dependencies import DB, CurrentUser
from app.core.security import verify_password, hash_password, create_access_token, create_refresh_token, decode_token
from app.models.user import User, RefreshToken, UserRole
from app.models.invitation import Invitation, InvitationStatus
from app.models.organization import Organization
from app.schemas.auth import (
    LoginRequest,
    SignUpRequest,
    TokenResponse,
    RefreshRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    AcceptInvitationRequest,
    InvitationDetailResponse,
)

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=TokenResponse)
async def register(req: SignUpRequest, db: DB):
    res = await db.execute(select(User).where(User.email == req.email.lower()))
    if res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email address already exists",
        )

    base_slug = re.sub(r'[^a-z0-9]+', '-', req.company_name.lower().strip()).strip('-') or "company"
    slug = f"{base_slug}-{uuid.uuid4().hex[:6]}"

    org_id = str(uuid.uuid4())
    org = Organization(
        id=org_id,
        name=req.company_name.strip() or "Client Organization",
        slug=slug,
    )
    db.add(org)

    new_user = User(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        email=req.email.lower(),
        name=req.name.strip(),
        hashed_password=hash_password(req.password),
        role=UserRole.CLIENT_ADMIN,
        is_active=True,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    token_data = {"sub": new_user.id, "org_id": new_user.organization_id, "role": new_user.role.value}
    access_token = create_access_token(token_data)
    refresh_token_str = create_refresh_token(token_data)

    ref_obj = RefreshToken(
        id=str(uuid.uuid4()),
        user_id=new_user.id,
        token_hash=refresh_token_str,
        expires_at=datetime.now(timezone.utc),
    )
    db.add(ref_obj)
    await db.commit()

    return TokenResponse(access_token=access_token, refresh_token=refresh_token_str)


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: DB):
    result = await db.execute(select(User).where(User.email == req.email.lower()))
    user = result.scalar_one_or_none()

    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    # Create tokens
    token_data = {"sub": user.id, "org_id": user.organization_id, "role": user.role.value}
    access_token = create_access_token(token_data)
    refresh_token_str = create_refresh_token(token_data)

    # Store refresh token in DB
    ref_obj = RefreshToken(
        id=str(uuid.uuid4()),
        user_id=user.id,
        token_hash=refresh_token_str,
        expires_at=datetime.now(timezone.utc),
    )
    db.add(ref_obj)
    await db.commit()

    return TokenResponse(access_token=access_token, refresh_token=refresh_token_str)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(req: RefreshRequest, db: DB):
    try:
        payload = decode_token(req.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id = payload.get("sub")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    res = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == req.refresh_token,
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at == None,
        )
    )
    db_token = res.scalar_one_or_none()
    if not db_token:
        raise HTTPException(status_code=401, detail="Refresh token revoked or invalid")

    res_user = await db.execute(select(User).where(User.id == user_id))
    user = res_user.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User inactive or missing")

    # Rotate refresh token
    db_token.revoked_at = datetime.now(timezone.utc)

    token_data = {"sub": user.id, "org_id": user.organization_id, "role": user.role.value}
    new_access = create_access_token(token_data)
    new_refresh = create_refresh_token(token_data)

    new_ref_obj = RefreshToken(
        id=str(uuid.uuid4()),
        user_id=user.id,
        token_hash=new_refresh,
        expires_at=datetime.now(timezone.utc),
    )
    db.add(new_ref_obj)
    await db.commit()

    return TokenResponse(access_token=new_access, refresh_token=new_refresh)


@router.post("/logout")
async def logout(req: RefreshRequest, db: DB):
    res = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == req.refresh_token))
    db_token = res.scalar_one_or_none()
    if db_token:
        db_token.revoked_at = datetime.now(timezone.utc)
        await db.commit()
    return {"message": "Successfully logged out"}


@router.get("/invitation/{token}", response_model=InvitationDetailResponse)
async def get_invitation_details(token: str, db: DB):
    res = await db.execute(select(Invitation).where(Invitation.token == token))
    inv = res.scalar_one_or_none()
    if not inv or inv.status != InvitationStatus.PENDING:
        raise HTTPException(status_code=404, detail="Invitation not found or expired")

    org_res = await db.execute(select(Organization).where(Organization.id == inv.organization_id))
    org = org_res.scalar_one_or_none()

    return InvitationDetailResponse(
        email=inv.email,
        name=inv.name,
        organization_name=org.name if org else "Unknown",
        role=inv.role.value,
    )


@router.post("/accept-invitation", response_model=TokenResponse)
async def accept_invitation(req: AcceptInvitationRequest, db: DB):
    res = await db.execute(select(Invitation).where(Invitation.token == req.token))
    inv = res.scalar_one_or_none()
    if not inv or inv.status != InvitationStatus.PENDING:
        raise HTTPException(status_code=400, detail="Invalid or expired invitation token")

    new_user = User(
        id=str(uuid.uuid4()),
        organization_id=inv.organization_id,
        email=inv.email.lower(),
        name=req.name,
        hashed_password=hash_password(req.password),
        role=inv.role,
        is_active=True,
    )
    db.add(new_user)

    inv.status = InvitationStatus.ACCEPTED
    inv.accepted_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(new_user)

    token_data = {"sub": new_user.id, "org_id": new_user.organization_id, "role": new_user.role.value}
    access_token = create_access_token(token_data)
    refresh_token_str = create_refresh_token(token_data)

    ref_obj = RefreshToken(
        id=str(uuid.uuid4()),
        user_id=new_user.id,
        token_hash=refresh_token_str,
        expires_at=datetime.now(timezone.utc),
    )
    db.add(ref_obj)
    await db.commit()

    return TokenResponse(access_token=access_token, refresh_token=refresh_token_str)


@router.post("/forgot-password")
async def forgot_password(req: ForgotPasswordRequest, db: DB):
    res = await db.execute(select(User).where(User.email == req.email.lower()))
    user = res.scalar_one_or_none()
    if user:
        reset_token = create_access_token({"sub": user.id, "type": "reset"})
        print(f"\n[DEV] Password reset link for {user.email}: http://localhost:8000/reset-password?token={reset_token}\n")
    return {"message": "If an account with that email exists, password reset instructions have been sent."}


@router.post("/reset-password")
async def reset_password(req: ResetPasswordRequest, db: DB):
    try:
        payload = decode_token(req.token)
        if payload.get("type") != "reset":
            raise HTTPException(status_code=400, detail="Invalid reset token")
        user_id = payload.get("sub")
    except Exception:
        raise HTTPException(status_code=400, detail="Expired or invalid reset token")

    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.hashed_password = hash_password(req.new_password)
    await db.commit()
    return {"message": "Password successfully reset"}
