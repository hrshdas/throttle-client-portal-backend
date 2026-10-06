"""
Analytics API — serves aggregated Meta Marketing API data to the Flutter client.

All endpoints:
- Derive organization from the authenticated JWT (never trusted from query params)
- Support range=7d|30d|90d shorthand OR explicit start/end date params
- Return zero-state (not errors) when no data exists for a period
- Calculate all derived metrics (CPM, CTR, CPC, CPL, ROAS) server-side

Endpoints:
  GET /analytics/overview     — aggregated account-level metrics
  GET /analytics/timeseries   — daily values for chart rendering
  GET /analytics/campaigns    — per-campaign breakdown
"""

from datetime import date, datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select, func, and_
from app.core.dependencies import DB, CurrentUser
from app.models.meta import (
    MetaConnection,
    MetaConnectionStatus,
    MetaCampaign,
    MetaDailyInsight,
    MetaInsightLevel,
)
from app.schemas.analytics import (
    AnalyticsOverviewResponse,
    AnalyticsPeriod,
    TimeSeriesPoint,
    CampaignAnalyticsResponse,
)
from app.services.meta_service import MetaService

router = APIRouter(prefix="/analytics", tags=["Analytics System"])


def _resolve_date_range(
    range_str: str | None,
    start: date | None,
    end: date | None,
) -> tuple[date, date]:
    """
    Resolve a (start, end) date pair from either:
    - range=7d|30d|90d shorthand (Flutter uses this)
    - Explicit start/end date params (custom ranges)

    range takes priority when both are supplied.
    Defaults to last 30 days if nothing is provided.
    """
    today = date.today()

    if range_str:
        mapping = {"7d": 7, "30d": 30, "90d": 90}
        days = mapping.get(range_str, 30)
        return today - timedelta(days=days), today

    return (
        start if start else today - timedelta(days=30),
        end if end else today,
    )


@router.get("/overview", response_model=AnalyticsOverviewResponse)
async def get_analytics_overview(
    current_user: CurrentUser,
    db: DB,
    range: str | None = Query(None, description="Shorthand range: 7d, 30d, 90d"),
    start: date | None = None,
    end: date | None = None,
    organization_id: str | None = None,
):
    """
    Fetch aggregated analytics metrics for the overview dashboard.

    Returns real numbers from synced Meta data. Returns zero-state if no data exists.
    Never returns NaN, Infinity, or fabricated values.
    """
    # ── Tenant isolation ───────────────────────────────────────────────────────
    target_org_id = current_user.organization_id
    if organization_id and current_user.role.value in ("THROTTLE_ADMIN", "THROTTLE_STAFF"):
        target_org_id = organization_id

    start_date, end_date = _resolve_date_range(range, start, end)

    # ── Connection status ──────────────────────────────────────────────────────
    conn_res = await db.execute(
        select(MetaConnection).where(MetaConnection.organization_id == target_org_id)
    )
    conn = conn_res.scalar_one_or_none()
    status_str = conn.status.value if conn else "DISCONNECTED"
    last_sync = conn.last_synced_at if conn else None

    # ── Aggregate account-level insights ──────────────────────────────────────
    query = (
        select(
            func.coalesce(func.sum(MetaDailyInsight.spend), 0.0),
            func.coalesce(func.sum(MetaDailyInsight.impressions), 0),
            func.coalesce(func.sum(MetaDailyInsight.reach), 0),
            func.coalesce(func.sum(MetaDailyInsight.clicks), 0),
            func.coalesce(func.sum(MetaDailyInsight.link_clicks), 0),
            func.coalesce(func.sum(MetaDailyInsight.leads), 0),
            func.coalesce(func.sum(MetaDailyInsight.conversions), 0),
            func.coalesce(func.sum(MetaDailyInsight.conversion_value), 0.0),
        )
        .where(
            and_(
                MetaDailyInsight.organization_id == target_org_id,
                MetaDailyInsight.level == MetaInsightLevel.ACCOUNT,
                MetaDailyInsight.date >= start_date,
                MetaDailyInsight.date <= end_date,
                MetaDailyInsight.meta_campaign_id.is_(None),
            )
        )
    )

    res = await db.execute(query)
    row = res.one()

    spend = float(row[0])
    impressions = int(row[1])
    reach = int(row[2])
    clicks = int(row[3])
    link_clicks = int(row[4])
    leads = int(row[5])
    conversions = int(row[6])
    raw_conv_value = float(row[7])
    conversion_value = raw_conv_value if raw_conv_value > 0 else None

    metrics = MetaService.calculate_safe_metrics(
        spend=spend,
        impressions=impressions,
        clicks=clicks,
        leads=leads,
        conversion_value=conversion_value,
    )

    return AnalyticsOverviewResponse(
        period=AnalyticsPeriod(start=start_date, end=end_date),
        spend=round(spend, 2),
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
        conversion_value=round(raw_conv_value, 2) if raw_conv_value > 0 else None,
        roas=metrics["roas"],
        last_synced_at=last_sync,
        connection_status=status_str,
    )


@router.get("/timeseries", response_model=list[TimeSeriesPoint])
async def get_analytics_timeseries(
    current_user: CurrentUser,
    db: DB,
    metric: str = Query("spend", description="Metric: spend, roas, cpm, ctr, cpc, cpl, leads, impressions, clicks"),
    range: str | None = Query(None, description="Shorthand range: 7d, 30d, 90d"),
    start: date | None = None,
    end: date | None = None,
    organization_id: str | None = None,
):
    """
    Fetch daily timeseries data for chart rendering.

    Flutter uses this for the line chart in InsightsScreen.
    Returns a list of {date, value} points ordered by date ascending.
    Unknown metrics default to 0.0 rather than erroring.
    """
    target_org_id = current_user.organization_id
    if organization_id and current_user.role.value in ("THROTTLE_ADMIN", "THROTTLE_STAFF"):
        target_org_id = organization_id

    start_date, end_date = _resolve_date_range(range, start, end)

    res = await db.execute(
        select(MetaDailyInsight)
        .where(
            and_(
                MetaDailyInsight.organization_id == target_org_id,
                MetaDailyInsight.level == MetaInsightLevel.ACCOUNT,
                MetaDailyInsight.date >= start_date,
                MetaDailyInsight.date <= end_date,
                MetaDailyInsight.meta_campaign_id.is_(None),
            )
        )
        .order_by(MetaDailyInsight.date.asc())
    )
    insights = res.scalars().all()

    points = []
    for i in insights:
        val: float = 0.0
        if metric == "spend":
            val = i.spend
        elif metric == "roas":
            val = i.roas or 0.0
        elif metric == "cpm":
            val = i.cpm or 0.0
        elif metric == "ctr":
            val = i.ctr or 0.0
        elif metric == "cpc":
            val = i.cpc or 0.0
        elif metric == "cpl":
            val = i.cpl or 0.0
        elif metric == "leads":
            val = float(i.leads)
        elif metric == "impressions":
            val = float(i.impressions)
        elif metric == "clicks":
            val = float(i.clicks)

        points.append(TimeSeriesPoint(date=i.date.isoformat(), value=round(val, 4)))

    return points


@router.get("/campaigns", response_model=list[CampaignAnalyticsResponse])
async def get_campaign_analytics(
    current_user: CurrentUser,
    db: DB,
    range: str | None = Query(None, description="Shorthand range: 7d, 30d, 90d"),
    start: date | None = None,
    end: date | None = None,
    organization_id: str | None = None,
):
    """
    Fetch per-campaign analytics breakdown.

    Aggregates MetaDailyInsight rows at CAMPAIGN level for the requested period.
    Returns real data — no hardcoded values.
    """
    target_org_id = current_user.organization_id
    if organization_id and current_user.role.value in ("THROTTLE_ADMIN", "THROTTLE_STAFF"):
        target_org_id = organization_id

    start_date, end_date = _resolve_date_range(range, start, end)

    # Fetch all campaigns for this org
    campaigns_res = await db.execute(
        select(MetaCampaign)
        .where(MetaCampaign.organization_id == target_org_id)
        .order_by(MetaCampaign.created_at.desc())
    )
    campaigns = campaigns_res.scalars().all()

    if not campaigns:
        return []

    result = []
    for campaign in campaigns:
        # Aggregate campaign-level daily insights
        agg = await db.execute(
            select(
                func.coalesce(func.sum(MetaDailyInsight.spend), 0.0),
                func.coalesce(func.sum(MetaDailyInsight.impressions), 0),
                func.coalesce(func.sum(MetaDailyInsight.clicks), 0),
                func.coalesce(func.sum(MetaDailyInsight.leads), 0),
                func.coalesce(func.sum(MetaDailyInsight.conversions), 0),
                func.coalesce(func.sum(MetaDailyInsight.conversion_value), 0.0),
            )
            .where(
                and_(
                    MetaDailyInsight.organization_id == target_org_id,
                    MetaDailyInsight.level == MetaInsightLevel.CAMPAIGN,
                    MetaDailyInsight.meta_campaign_id == campaign.meta_campaign_id,
                    MetaDailyInsight.date >= start_date,
                    MetaDailyInsight.date <= end_date,
                )
            )
        )
        agg_row = agg.one()

        spend = float(agg_row[0])
        impressions = int(agg_row[1])
        clicks = int(agg_row[2])
        leads = int(agg_row[3])
        conversions = int(agg_row[4])
        raw_cv = float(agg_row[5])
        conversion_value = raw_cv if raw_cv > 0 else None

        metrics = MetaService.calculate_safe_metrics(
            spend=spend,
            impressions=impressions,
            clicks=clicks,
            leads=leads,
            conversion_value=conversion_value,
        )

        result.append(
            CampaignAnalyticsResponse(
                id=campaign.id,
                meta_campaign_id=campaign.meta_campaign_id,
                name=campaign.name,
                status=campaign.status,
                spend=round(spend, 2),
                impressions=impressions,
                clicks=clicks,
                ctr=metrics["ctr"],
                cpc=metrics["cpc"],
                cpm=metrics["cpm"],
                leads=leads,
                cpl=metrics["cpl"],
                roas=metrics["roas"],
            )
        )

    return result
