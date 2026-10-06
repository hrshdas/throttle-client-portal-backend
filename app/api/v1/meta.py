"""
Meta OAuth and connection management routes.

Security design:
- OAuth state is generated server-side and stored in oauth_state.py (single-use, time-limited)
- The callback validates state before processing any Meta code exchange
- Meta access tokens are NEVER returned to Flutter or logged
- Organization is ALWAYS derived from the authenticated JWT session
- Only THROTTLE_ADMIN/STAFF can override organization_id query param

Endpoints:
  POST  /meta/connect/start       — generate Meta OAuth URL + state
  GET   /meta/connect/callback    — browser redirect from Meta after auth
  GET   /meta/ad-accounts         — list accessible ad accounts
  POST  /meta/select-ad-account   — finalize account selection + trigger sync
  GET   /meta/connection          — current connection status
  POST  /meta/sync                — manual sync trigger
  POST  /meta/disconnect          — disconnect Meta account
"""

import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, Query, status
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy import select
from app.core.dependencies import DB, CurrentUser
from app.core.config import get_settings
from app.core.crypto import encrypt_message, decrypt_message
from app.core.oauth_state import generate_state, validate_state
from app.models.meta import MetaConnection, MetaConnectionStatus
from app.schemas.meta import (
    MetaConnectionResponse,
    MetaSelectAdAccountRequest,
    MetaAdAccountResponse,
    MetaConnectStartResponse,
)
from app.services.meta_service import MetaService, MetaServiceError
from app.services.meta_api_client import MetaApiClient, MetaApiError
from app.services.meta_sync_service import sync_organization_meta

router = APIRouter(prefix="/meta", tags=["Meta Connection"])
settings = get_settings()
logger = logging.getLogger(__name__)


@router.post("/demo-connect", response_model=MetaConnectionResponse)
async def demo_connect_meta(current_user: CurrentUser, db: DB):
    """
    Connect a demo Meta Ad Account for local testing.
    Populates realistic campaign analytics in ₹ INR without requiring a live Meta OAuth app approval.
    """
    encrypted_token = encrypt_message("mock_demo_access_token")
    
    res = await db.execute(
        select(MetaConnection).where(MetaConnection.organization_id == current_user.organization_id)
    )
    conn = res.scalar_one_or_none()

    if conn:
        conn.encrypted_access_token = encrypted_token
        conn.ad_account_id = "act_15931400323077"
        conn.ad_account_name = "Throttle Demo Ad Account (₹ INR)"
        conn.status = MetaConnectionStatus.CONNECTED
        conn.error_message = None
    else:
        conn = MetaConnection(
            organization_id=current_user.organization_id,
            encrypted_access_token=encrypted_token,
            ad_account_id="act_15931400323077",
            ad_account_name="Throttle Demo Ad Account (₹ INR)",
            status=MetaConnectionStatus.CONNECTED,
        )
        db.add(conn)

    await db.commit()
    
    # Trigger sync to populate daily insights
    updated_conn = await sync_organization_meta(db, current_user.organization_id)
    return updated_conn


@router.post("/connect/start", response_model=MetaConnectStartResponse)
async def start_meta_connect(current_user: CurrentUser):
    """
    Generate a Meta OAuth authorization URL for the authenticated user's organization.

    The state parameter is cryptographically random and stored server-side.
    It binds the OAuth callback to this specific organization (CSRF protection).
    """
    state = generate_state(current_user.organization_id)
    auth_url = MetaService.get_auth_url(state=state)
    logger.info("Meta OAuth flow started for org=%s", current_user.organization_id)
    return MetaConnectStartResponse(auth_url=auth_url, state=state)


@router.get("/connect/callback")
async def meta_connect_callback(
    db: DB,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
):
    """
    OAuth callback — Meta redirects the browser here after the user authorizes.

    Security:
    - Validates state against server-side store (CSRF protection)
    - Exchanges short-lived code for a long-lived token (~60 days)
    - Stores only encrypted token — never returns it to Flutter
    - Redirects browser to frontend on success/failure
    """
    # ── User denied / error from Meta ─────────────────────────────────────────
    if error:
        logger.warning("Meta OAuth error: %s — %s", error, error_description)
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/meta-connected?status=error&reason=user_denied"
        )

    # ── Missing parameters ─────────────────────────────────────────────────────
    if not code or not state:
        logger.warning("Meta OAuth callback missing code or state")
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/meta-connected?status=error&reason=missing_params"
        )

    # ── Validate state (CSRF check) ────────────────────────────────────────────
    organization_id = validate_state(state)
    if not organization_id:
        logger.warning("Meta OAuth callback: invalid or expired state (possible CSRF attack)")
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/meta-connected?status=error&reason=invalid_state"
        )

    try:
        # ── Exchange code for short-lived token ────────────────────────────────
        token_data = await MetaService.exchange_code_for_token(code)
        short_lived_token = token_data.get("access_token", "")
        if not short_lived_token:
            raise MetaServiceError("No access token in Meta response")

        # ── Exchange for long-lived token (60 days) ────────────────────────────
        client = MetaApiClient(access_token=short_lived_token, api_version=settings.META_API_VERSION)
        try:
            ll_data = await client.exchange_for_long_lived_token()
            access_token = ll_data.get("access_token", short_lived_token)
            token_expires_in = ll_data.get("expires_in")  # seconds
        except MetaApiError:
            # Fallback to short-lived if exchange fails (e.g., dev environment)
            access_token = short_lived_token
            token_expires_in = None
            logger.warning("Could not exchange for long-lived token; using short-lived token")

        # ── Fetch Meta user info ───────────────────────────────────────────────
        client = MetaApiClient(access_token=access_token, api_version=settings.META_API_VERSION)
        try:
            me = await client.get_me()
            meta_user_id = me.get("id")
        except MetaApiError:
            meta_user_id = None

        # ── Calculate token expiry ─────────────────────────────────────────────
        token_expires_at = None
        if token_expires_in:
            token_expires_at = datetime.fromtimestamp(
                datetime.now(timezone.utc).timestamp() + int(token_expires_in),
                tz=timezone.utc,
            )

        # ── Encrypt and store connection ───────────────────────────────────────
        encrypted_token = encrypt_message(access_token)

        res = await db.execute(
            select(MetaConnection).where(MetaConnection.organization_id == organization_id)
        )
        conn = res.scalar_one_or_none()

        if conn:
            conn.encrypted_access_token = encrypted_token
            conn.token_expires_at = token_expires_at
            conn.meta_user_id = meta_user_id
            conn.status = MetaConnectionStatus.CONNECTED
            conn.error_message = None
        else:
            conn = MetaConnection(
                organization_id=organization_id,
                encrypted_access_token=encrypted_token,
                token_expires_at=token_expires_at,
                meta_user_id=meta_user_id,
                status=MetaConnectionStatus.CONNECTED,
            )
            db.add(conn)

        await db.commit()
        logger.info("Meta OAuth connection created/updated for org=%s", organization_id)

        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/meta-connected?status=success"
        )

    except (MetaServiceError, MetaApiError) as exc:
        logger.error("Meta OAuth callback error for org=%s: %s", organization_id, exc)
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/meta-connected?status=error&reason=api_error"
        )
    except Exception as exc:
        logger.error("Unexpected error in Meta callback for org=%s: %s", organization_id, exc, exc_info=True)
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/meta-connected?status=error&reason=server_error"
        )


@router.get("/ad-accounts", response_model=list[MetaAdAccountResponse])
async def list_ad_accounts(current_user: CurrentUser, db: DB):
    """
    List Meta ad accounts accessible to the connected user.

    The organization is derived from the authenticated JWT session — never from query params.
    """
    res = await db.execute(
        select(MetaConnection).where(MetaConnection.organization_id == current_user.organization_id)
    )
    conn = res.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Meta account not connected.")

    raw_token = decrypt_message(conn.encrypted_access_token)

    try:
        client = MetaApiClient(access_token=raw_token, api_version=settings.META_API_VERSION)
        accounts = await client.get_ad_accounts()
    except MetaApiError as exc:
        logger.error("Failed to fetch ad accounts for org=%s: %s", current_user.organization_id, exc)
        raise HTTPException(status_code=502, detail="Could not retrieve ad accounts from Meta.")

    return [
        MetaAdAccountResponse(
            id=acc.get("id", ""),
            name=acc.get("name", "Ad Account"),
            currency=acc.get("currency", "USD"),
        )
        for acc in accounts
        if acc.get("id")
    ]


@router.post("/select-ad-account", response_model=MetaConnectionResponse)
async def select_ad_account(
    req: MetaSelectAdAccountRequest,
    current_user: CurrentUser,
    db: DB,
):
    """
    Finalize ad account selection and trigger an initial 30-day historical sync.

    Security: validates that the selected account is actually accessible via the
    authenticated Meta connection (not blindly trusted from Flutter).
    """
    res = await db.execute(
        select(MetaConnection).where(MetaConnection.organization_id == current_user.organization_id)
    )
    conn = res.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Meta account not connected.")

    # ── Validate ad account is accessible ────────────────────────────────────
    raw_token = decrypt_message(conn.encrypted_access_token)
    try:
        client = MetaApiClient(access_token=raw_token, api_version=settings.META_API_VERSION)
        accounts = await client.get_ad_accounts()
        accessible_ids = {acc.get("id") for acc in accounts}
        # Normalize: check with and without "act_" prefix
        normalized_request_id = req.ad_account_id
        if not normalized_request_id.startswith("act_"):
            normalized_request_id = f"act_{normalized_request_id}"

        if accessible_ids and normalized_request_id not in accessible_ids:
            logger.warning(
                "org=%s tried to select inaccessible ad account %s",
                current_user.organization_id,
                req.ad_account_id,
            )
            raise HTTPException(
                status_code=403,
                detail="Selected ad account is not accessible through your Meta connection.",
            )
    except MetaApiError:
        # If we can't validate (network error), allow in dev mode; block in prod
        if settings.is_production:
            raise HTTPException(status_code=502, detail="Could not verify ad account access.")
        logger.warning("DEV MODE: Skipping ad account validation due to Meta API error")

    conn.ad_account_id = req.ad_account_id
    if req.ad_account_name:
        conn.ad_account_name = req.ad_account_name
    await db.commit()

    logger.info("Ad account %s selected for org=%s; triggering sync", req.ad_account_id, current_user.organization_id)

    # Trigger initial historical sync
    updated_conn = await sync_organization_meta(db, current_user.organization_id)
    return updated_conn


@router.get("/connection", response_model=MetaConnectionResponse)
async def get_meta_connection(
    current_user: CurrentUser,
    db: DB,
    organization_id: str | None = None,
):
    """
    Fetch Meta connection status for the authenticated user's organization.

    THROTTLE_ADMIN/STAFF may pass organization_id to view another org's status.
    Response NEVER includes access tokens.
    """
    target_org_id = current_user.organization_id
    if organization_id and current_user.role.value in ("THROTTLE_ADMIN", "THROTTLE_STAFF"):
        target_org_id = organization_id

    res = await db.execute(
        select(MetaConnection).where(MetaConnection.organization_id == target_org_id)
    )
    conn = res.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Meta account not connected.")

    return conn


@router.post("/sync", response_model=MetaConnectionResponse)
async def trigger_meta_sync(
    current_user: CurrentUser,
    db: DB,
    organization_id: str | None = None,
):
    """
    Manually trigger a Meta data synchronization.

    Always scoped to the authenticated user's organization.
    THROTTLE_ADMIN/STAFF may pass organization_id to sync on behalf of a client.
    """
    target_org_id = current_user.organization_id
    if organization_id and current_user.role.value in ("THROTTLE_ADMIN", "THROTTLE_STAFF"):
        target_org_id = organization_id

    try:
        updated_conn = await sync_organization_meta(db, target_org_id)
        return updated_conn
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except MetaApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/disconnect")
async def disconnect_meta(current_user: CurrentUser, db: DB):
    """
    Disconnect Meta advertising account for the authenticated organization.
    Preserves historical analytics data — does not delete insights.
    """
    res = await db.execute(
        select(MetaConnection).where(MetaConnection.organization_id == current_user.organization_id)
    )
    conn = res.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Meta account not connected.")

    conn.status = MetaConnectionStatus.DISCONNECTED
    await db.commit()
    logger.info("Meta disconnected for org=%s", current_user.organization_id)
    return {"message": "Meta account disconnected successfully."}
