"""
Meta Sync Service — synchronizes Meta Marketing API data into PostgreSQL.

Architecture:
  MetaApiClient (real HTTP) → sync_organization_meta (this file) → PostgreSQL

Development mode:
  When ENVIRONMENT=development AND Meta credentials are placeholder values,
  realistic demo data is generated instead of calling Meta.
  Production NEVER silently falls back to fake data.

Idempotency:
  All upsert operations are idempotent — running sync twice produces no duplicates.
"""

import logging
import math
from datetime import date, datetime, timedelta, timezone
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.crypto import decrypt_message
from app.models.meta import (
    MetaConnection,
    MetaConnectionStatus,
    MetaCampaign,
    MetaAdSet,
    MetaAd,
    MetaDailyInsight,
    MetaInsightLevel,
)
from app.services.meta_service import MetaService
from app.services.meta_api_client import MetaApiClient, MetaApiError, parse_meta_actions

logger = logging.getLogger(__name__)
settings = get_settings()


# ─── Main Entry Point ──────────────────────────────────────────────────────────

async def sync_organization_meta(
    db: AsyncSession,
    organization_id: str,
    days_back: int | None = None,
) -> MetaConnection:
    """
    Synchronize Meta Marketing API data for an organization.

    1. Fetch MetaConnection record and decrypt token
    2. Set status → SYNCING
    3. Sync campaigns, ad sets, ads from Meta
    4. Sync daily insights for the requested date window
    5. Set status → SYNCED, update last_synced_at
    6. On error: set status → ERROR, store safe error message

    Args:
        db: Async SQLAlchemy session
        organization_id: Authenticated org ID (from JWT — never trust client)
        days_back: Override for historical days (defaults to META_HISTORICAL_DAYS)

    Returns:
        Updated MetaConnection record
    """
    if days_back is None:
        days_back = settings.META_HISTORICAL_DAYS

    # ── 1. Fetch connection ────────────────────────────────────────────────────
    res = await db.execute(
        select(MetaConnection).where(MetaConnection.organization_id == organization_id)
    )
    conn = res.scalar_one_or_none()
    if not conn:
        raise ValueError(f"No Meta connection found for organization {organization_id}")
    if conn.status == MetaConnectionStatus.DISCONNECTED:
        raise ValueError("Meta connection is disconnected.")

    # ── 2. Mark as syncing ─────────────────────────────────────────────────────
    conn.status = MetaConnectionStatus.SYNCING
    conn.error_message = None
    await db.commit()

    try:
        raw_token = decrypt_message(conn.encrypted_access_token)
        ad_account_id = conn.ad_account_id or "act_default"

        today = date.today()
        start_date = today - timedelta(days=days_back)

        # ── 3. Choose real vs. dev mode ────────────────────────────────────────
        if settings.meta_is_configured and not raw_token.startswith("mock_"):
            logger.info("Syncing real Meta data for org=%s, account=%s, days_back=%d",
                        organization_id, ad_account_id, days_back)
            # Purge any previous demo/seed records for this organization so real account status is reflected accurately
            from sqlalchemy import delete
            await db.execute(delete(MetaDailyInsight).where(MetaDailyInsight.organization_id == organization_id))
            await db.execute(delete(MetaCampaign).where(MetaCampaign.organization_id == organization_id))
            await db.commit()

            client = MetaApiClient(access_token=raw_token, api_version=settings.META_API_VERSION)
            await _sync_campaigns_real(client, db, organization_id, ad_account_id)
            await _sync_insights_real(client, db, organization_id, ad_account_id, start_date, today)
        else:
            # Development mode — generate realistic demo data
            if settings.is_production:
                raise RuntimeError(
                    "Meta credentials are not configured but ENVIRONMENT=production. "
                    "Set META_APP_ID and META_APP_SECRET in .env before going live."
                )
            logger.info(
                "DEV MODE: Generating demo data for org=%s (set META_APP_ID/META_APP_SECRET for real data)",
                organization_id,
            )
            await _sync_campaigns_dev(db, organization_id, ad_account_id)
            await _sync_insights_dev(db, organization_id, ad_account_id, start_date, today)

        # ── 4. Finalize ────────────────────────────────────────────────────────
        conn.status = MetaConnectionStatus.SYNCED
        conn.last_synced_at = datetime.now(timezone.utc)
        conn.error_message = None
        await db.commit()
        await db.refresh(conn)

        logger.info("Meta sync completed for org=%s", organization_id)
        return conn

    except MetaApiError as exc:
        logger.error("Meta API error during sync for org=%s: %s", organization_id, exc)
        conn.status = MetaConnectionStatus.ERROR
        conn.error_message = str(exc)
        await db.commit()
        raise

    except Exception as exc:
        logger.error("Unexpected error during Meta sync for org=%s: %s", organization_id, exc, exc_info=True)
        conn.status = MetaConnectionStatus.ERROR
        conn.error_message = "An unexpected error occurred during synchronization."
        await db.commit()
        raise


# ─── Real API Sync Functions ───────────────────────────────────────────────────

async def _sync_campaigns_real(
    client: MetaApiClient,
    db: AsyncSession,
    organization_id: str,
    ad_account_id: str,
) -> None:
    """Fetch and upsert campaigns from Meta API."""
    raw_campaigns = await client.get_campaigns(ad_account_id)
    logger.info("Fetched %d campaigns from Meta for org=%s", len(raw_campaigns), organization_id)

    for raw in raw_campaigns:
        meta_campaign_id = raw.get("id", "")
        if not meta_campaign_id:
            continue

        # Check existing
        res = await db.execute(
            select(MetaCampaign).where(
                and_(
                    MetaCampaign.organization_id == organization_id,
                    MetaCampaign.meta_campaign_id == meta_campaign_id,
                )
            )
        )
        campaign = res.scalar_one_or_none()

        name = raw.get("name", "Unnamed Campaign")
        status = raw.get("status", "ACTIVE")
        objective = raw.get("objective")

        if campaign:
            campaign.name = name
            campaign.status = status
            campaign.objective = objective
        else:
            campaign = MetaCampaign(
                organization_id=organization_id,
                ad_account_id=ad_account_id,
                meta_campaign_id=meta_campaign_id,
                name=name,
                status=status,
                objective=objective,
            )
            db.add(campaign)

    await db.flush()


async def _sync_insights_real(
    client: MetaApiClient,
    db: AsyncSession,
    organization_id: str,
    ad_account_id: str,
    start_date: date,
    end_date: date,
) -> None:
    """Fetch and upsert daily insights from Meta API at account and campaign level."""
    date_start_str = start_date.isoformat()
    date_end_str = end_date.isoformat()

    # ── Account-level insights ─────────────────────────────────────────────────
    raw_account = await client.get_insights(
        ad_account_id, date_start_str, date_end_str, level="account"
    )
    logger.info("Fetched %d account-level insight rows for org=%s", len(raw_account), organization_id)

    for row in raw_account:
        await _upsert_insight(
            db=db,
            organization_id=organization_id,
            ad_account_id=ad_account_id,
            level=MetaInsightLevel.ACCOUNT,
            insight_date=_parse_date(row.get("date_start", "")),
            row=row,
            meta_campaign_id=None,
        )

    # ── Campaign-level insights ────────────────────────────────────────────────
    raw_campaigns = await client.get_insights(
        ad_account_id, date_start_str, date_end_str, level="campaign"
    )
    logger.info("Fetched %d campaign-level insight rows for org=%s", len(raw_campaigns), organization_id)

    for row in raw_campaigns:
        await _upsert_insight(
            db=db,
            organization_id=organization_id,
            ad_account_id=ad_account_id,
            level=MetaInsightLevel.CAMPAIGN,
            insight_date=_parse_date(row.get("date_start", "")),
            row=row,
            meta_campaign_id=row.get("campaign_id"),
        )

    await db.flush()


async def _upsert_insight(
    db: AsyncSession,
    organization_id: str,
    ad_account_id: str,
    level: MetaInsightLevel,
    insight_date: date | None,
    row: dict,
    meta_campaign_id: str | None,
) -> None:
    """Upsert a single MetaDailyInsight from a raw Meta API row."""
    if not insight_date:
        return

    spend = float(row.get("spend", 0) or 0)
    impressions = int(row.get("impressions", 0) or 0)
    reach = int(row.get("reach", 0) or 0)
    clicks = int(row.get("clicks", 0) or 0)
    link_clicks = int(row.get("inline_link_clicks", 0) or 0)

    actions = row.get("actions")
    action_values = row.get("action_values")
    leads, conversions, conversion_value = parse_meta_actions(actions, action_values)

    metrics = MetaService.calculate_safe_metrics(
        spend=spend,
        impressions=impressions,
        clicks=clicks,
        leads=leads,
        conversion_value=conversion_value,
    )

    # Build WHERE clause
    filters = [
        MetaDailyInsight.organization_id == organization_id,
        MetaDailyInsight.level == level,
        MetaDailyInsight.date == insight_date,
    ]
    if meta_campaign_id:
        filters.append(MetaDailyInsight.meta_campaign_id == meta_campaign_id)
    else:
        filters.append(MetaDailyInsight.meta_campaign_id.is_(None))

    res = await db.execute(select(MetaDailyInsight).where(and_(*filters)))
    insight = res.scalar_one_or_none()

    fields = dict(
        spend=spend,
        impressions=impressions,
        reach=reach,
        clicks=clicks,
        link_clicks=link_clicks,
        ctr=metrics["ctr"],
        cpc=metrics["cpc"],
        cpm=metrics["cpm"],
        leads=leads,
        cpl=metrics["cpl"],
        conversions=conversions,
        conversion_value=conversion_value,
        roas=metrics["roas"],
        raw_actions=actions,
    )

    if insight:
        for k, v in fields.items():
            setattr(insight, k, v)
    else:
        insight = MetaDailyInsight(
            organization_id=organization_id,
            ad_account_id=ad_account_id,
            meta_campaign_id=meta_campaign_id,
            level=level,
            date=insight_date,
            **fields,
        )
        db.add(insight)


# ─── Development Mode Fallback ─────────────────────────────────────────────────

async def _sync_campaigns_dev(
    db: AsyncSession,
    organization_id: str,
    ad_account_id: str,
) -> None:
    """Create realistic demo campaigns (development mode only)."""
    dev_campaigns = [
        ("cmp_growth_01", "Q3 Performance Max — Conversions & Retargeting", "ACTIVE", "OUTCOME_SALES"),
        ("cmp_leads_02", "High-Intent Lead Gen Campaign", "ACTIVE", "OUTCOME_LEADS"),
        ("cmp_brand_03", "Brand Awareness — Video Views", "PAUSED", "OUTCOME_AWARENESS"),
    ]

    for meta_id, name, status, objective in dev_campaigns:
        res = await db.execute(
            select(MetaCampaign).where(
                and_(
                    MetaCampaign.organization_id == organization_id,
                    MetaCampaign.meta_campaign_id == meta_id,
                )
            )
        )
        existing = res.scalar_one_or_none()
        if not existing:
            db.add(MetaCampaign(
                organization_id=organization_id,
                ad_account_id=ad_account_id,
                meta_campaign_id=meta_id,
                name=name,
                status=status,
                objective=objective,
            ))

    await db.flush()


async def _sync_insights_dev(
    db: AsyncSession,
    organization_id: str,
    ad_account_id: str,
    start_date: date,
    end_date: date,
) -> None:
    """Generate realistic daily account-level insights (development mode only)."""
    current_d = start_date
    day_idx = 0

    while current_d <= end_date:
        # Deterministic but realistic values using sine-wave variation
        base_spend = 480.0 + (day_idx * 8.5) + (math.sin(day_idx * 0.7) * 95.0)
        spend = round(max(220.0, base_spend), 2)
        impressions = int(spend * 22.0 + math.cos(day_idx) * 200)
        reach = int(impressions * 0.71)
        clicks = int(impressions * 0.024)
        link_clicks = int(clicks * 0.83)
        leads = int(clicks * 0.044)
        conversions = int(leads * 0.62)
        conversion_value = round(spend * 4.1 + math.sin(day_idx) * 50.0, 2)

        metrics = MetaService.calculate_safe_metrics(
            spend=spend,
            impressions=impressions,
            clicks=clicks,
            leads=leads,
            conversion_value=conversion_value,
        )

        # Upsert account-level row
        res = await db.execute(
            select(MetaDailyInsight).where(
                and_(
                    MetaDailyInsight.organization_id == organization_id,
                    MetaDailyInsight.level == MetaInsightLevel.ACCOUNT,
                    MetaDailyInsight.date == current_d,
                    MetaDailyInsight.meta_campaign_id.is_(None),
                )
            )
        )
        insight = res.scalar_one_or_none()

        values = dict(
            spend=spend,
            impressions=impressions,
            reach=reach,
            clicks=clicks,
            link_clicks=link_clicks,
            ctr=metrics["ctr"],
            cpc=metrics["cpc"],
            cpm=metrics["cpm"],
            leads=leads,
            cpl=metrics["cpl"],
            conversions=conversions,
            conversion_value=conversion_value,
            roas=metrics["roas"],
        )

        if insight:
            for k, v in values.items():
                setattr(insight, k, v)
        else:
            db.add(MetaDailyInsight(
                organization_id=organization_id,
                ad_account_id=ad_account_id,
                level=MetaInsightLevel.ACCOUNT,
                date=current_d,
                **values,
            ))

        current_d += timedelta(days=1)
        day_idx += 1

    await db.flush()


# ─── Utilities ────────────────────────────────────────────────────────────────

def _parse_date(date_str: str) -> date | None:
    """Parse a YYYY-MM-DD string into a date object. Returns None on failure."""
    try:
        return date.fromisoformat(date_str)
    except (ValueError, TypeError):
        return None
